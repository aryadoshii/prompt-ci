import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { ApiClient } from './apiClient';
import { GitClient } from './gitClient';
import { NotificationHandler } from './notificationHandler';
import { SidebarProvider } from './sidebarProvider';
import { HistoryProvider } from './historyProvider';

export class PromptWatcher {
    private gitClient: GitClient;
    private watchers: vscode.FileSystemWatcher[] = [];
    private saveListener?: vscode.Disposable;
    private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
    private activeRunIds: Set<string> = new Set(); // prevent polling same run twice

    constructor(
        private apiClient: ApiClient,
        private notificationHandler: NotificationHandler,
        private sidebarProvider: SidebarProvider,
        private historyProvider: HistoryProvider
    ) {
        this.gitClient = new GitClient();
    }

    start(): void {
        const config = vscode.workspace.getConfiguration('promptci');
        const patterns = config.get<string[]>('promptFilePatterns',
            ['**/*.prompt', '**/prompts/**/*.txt', '**/system_prompt.txt']);

        // Exclude promptci.yaml itself — it's config, not a prompt file
        const promptPatterns = patterns.filter(p => !p.includes('promptci.yaml'));

        promptPatterns.forEach(pattern => {
            const watcher = vscode.workspace.createFileSystemWatcher(pattern);
            watcher.onDidChange(uri => this.onPromptFileChangedDebounced(uri));
            this.watchers.push(watcher);
        });

        this.saveListener = vscode.workspace.onDidSaveTextDocument((document) => {
            if (this.matchesPromptFile(document.uri)) {
                this.onPromptFileChangedDebounced(document.uri);
            }
        });
    }

    dispose(): void {
        this.watchers.forEach(w => w.dispose());
        this.watchers = [];
        this.saveListener?.dispose();
        this.saveListener = undefined;
        this.debounceTimers.forEach(t => clearTimeout(t));
        this.debounceTimers.clear();
    }

    private onPromptFileChangedDebounced(uri: vscode.Uri): void {
        // VS Code fires onDidChange multiple times per save — coalesce into one call
        const key = uri.fsPath;
        const existing = this.debounceTimers.get(key);
        if (existing) {
            clearTimeout(existing);
        }
        const timer = setTimeout(() => {
            this.debounceTimers.delete(key);
            this.onPromptFileChanged(uri);
        }, 800); // 800ms quiet period — one save = one run
        this.debounceTimers.set(key, timer);
    }

    async onPromptFileChanged(uri: vscode.Uri): Promise<void> {
        const activeDocument = vscode.workspace.textDocuments.find((doc) => doc.uri.toString() === uri.toString());
        const promptTextOverride = activeDocument?.isDirty ? activeDocument.getText() : undefined;
        await this.runForUri(uri, promptTextOverride, false);
    }

    async runManually(): Promise<void> {
        // Triggered by command palette
        const activeEditor = vscode.window.activeTextEditor;
        if (activeEditor) {
            await this.runForUri(
                activeEditor.document.uri,
                activeEditor.document.getText(),
                true
            );
        } else {
            vscode.window.showInformationMessage('PromptCI: No active text editor open.');
        }
    }

    async diagnoseSetup(): Promise<void> {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const activeEditor = vscode.window.activeTextEditor;

        if (!workspaceRoot) {
            vscode.window.showErrorMessage('PromptCI: No workspace folder is open.');
            return;
        }

        const activePath = activeEditor?.document.uri.fsPath || '(none)';
        const testSuitePath = activeEditor ? this.findTestSuitePath(workspaceRoot, activeEditor.document.uri.fsPath) : null;
        const isTracked = activeEditor ? await this.gitClient.isTracked(workspaceRoot, activeEditor.document.uri.fsPath) : false;
        const headVersion = activeEditor ? await this.gitClient.getHeadVersion(workspaceRoot, activeEditor.document.uri.fsPath) : null;

        const health = await this.apiClient.checkHealth().catch((error: any) => ({
            status: 'error',
            error: error?.message || 'Unknown backend error',
        }));

        const lines = [
            `Workspace: ${workspaceRoot}`,
            `Active editor: ${activePath}`,
            `PromptCI config: ${testSuitePath || 'not found'}`,
            `Git tracked: ${isTracked ? 'yes' : 'no'}`,
            `HEAD baseline: ${headVersion ? 'found' : 'missing'}`,
            `Backend: ${health.status === 'ok' ? 'reachable' : `unreachable (${health.error || 'unknown error'})`}`,
        ];

        outputMessage(lines.join('\n'));
        vscode.window.showInformationMessage('PromptCI: Setup diagnosis written to the PromptCI output channel.', 'Open Output').then((choice) => {
            if (choice === 'Open Output') {
                outputMessage('', true);
            }
        });
    }

    private async runForUri(
        uri: vscode.Uri,
        promptV2Override?: string,
        showNoOpMessages: boolean = false
    ): Promise<void> {
        // 1. Get workspace root
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!workspaceRoot) {
            if (showNoOpMessages) {
                vscode.window.showErrorMessage('PromptCI: No workspace folder is open.');
            }
            return;
        }

        // 2. Read current file content (v2)
        const promptV2 = promptV2Override ?? fs.readFileSync(uri.fsPath, 'utf8');

        // 3. Get previous version via git diff HEAD
        const promptV1 = await this.gitClient.getHeadVersion(
            workspaceRoot, 
            uri.fsPath
        );
        
        // If no HEAD version (new file) or identical → skip
        if (!promptV1) {
            if (showNoOpMessages) {
                vscode.window.showWarningMessage(
                    'PromptCI: This file has no committed HEAD version yet. Commit it once to create a baseline before running tests.'
                );
            }
            return;
        }

        if (promptV1 === promptV2) {
            if (showNoOpMessages) {
                vscode.window.showInformationMessage(
                    'PromptCI: No changes detected against git HEAD for the active prompt file.'
                );
            }
            return;
        }

        // 4. Find promptci.yaml test suite
        const testSuite = this.findTestSuite(workspaceRoot, uri.fsPath);
        if (!testSuite) {
            vscode.window.showWarningMessage(
                'PromptCI: No promptci.yaml found. Create one to enable regression testing.'
            );
            return;
        }

        // 5. Notify user that tests are starting
        vscode.window.showInformationMessage(
            `PromptCI: Detected change in ${path.basename(uri.fsPath)}. Running regression tests...`
        );

        // 6. Update sidebar to "running" state
        this.sidebarProvider.setRunning(true);

        // 7. Call backend API
        try {
            const config = vscode.workspace.getConfiguration('promptci');
            const runResult = await this.apiClient.startRun({
                prompt_v1: promptV1,
                prompt_v2: promptV2,
                prompt_file: uri.fsPath,
                test_suite: testSuite,
                repo_path: workspaceRoot,
                notify_email: config.get<string>('notifyEmail', '')
            });

            // 8. Poll for completion (guard: ignore if already tracking this run)
            if (!this.activeRunIds.has(runResult.run_id)) {
                this.activeRunIds.add(runResult.run_id);
                await this.pollForCompletion(runResult.run_id, uri.fsPath);
            }
        } catch (error: any) {
            this.sidebarProvider.setRunning(false);
            vscode.window.showErrorMessage(`PromptCI Request Failed: Ensure the backend is running. ${error.message}`);
        }
    }

    async pollForCompletion(runId: string, promptFile: string): Promise<void> {
        let attempts = 0;
        const maxAttempts = 300; // 10 minutes max assuming 2s interval
        
        const pollInterval = setInterval(async () => {
            attempts++;
            if (attempts > maxAttempts) {
                clearInterval(pollInterval);
                this.sidebarProvider.setRunning(false);
                vscode.window.showErrorMessage(`PromptCI: Pipeline timeout after 10 minutes.`);
                return;
            }
            
            try {
                const results = await this.apiClient.getRun(runId);
                const runInfo = results.run || results; // Handle payload wrapper if present
                
                if (runInfo.status === 'complete') {
                    clearInterval(pollInterval);
                    this.activeRunIds.delete(runId);
                    this.sidebarProvider.setRunning(false);
                    this.sidebarProvider.updateResults(results);
                    void this.historyProvider.refresh();
                    await this.notificationHandler.showResult(results, promptFile);
                } else if (runInfo.status === 'failed') {
                    clearInterval(pollInterval);
                    this.activeRunIds.delete(runId);
                    this.sidebarProvider.setRunning(false);
                    void this.historyProvider.refresh();
                    vscode.window.showErrorMessage(
                        `PromptCI: Pipeline failed. Check backend logs.`
                    );
                }
            } catch (e) {
                // Ignore temporary fetch errors during polling
            }
        }, 2000);   // poll every 2 seconds
    }

    private findTestSuite(workspaceRoot: string, promptFile: string): any {
        // Look for promptci.yaml in: same dir, .promptci/, project root
        const locations = this.getTestSuiteLocations(workspaceRoot, promptFile);
        
        for (const loc of locations) {
            if (fs.existsSync(loc)) {
                return this.parseYaml(loc);
            }
        }
        return null;
    }

    private findTestSuitePath(workspaceRoot: string, promptFile: string): string | null {
        const locations = this.getTestSuiteLocations(workspaceRoot, promptFile);
        return locations.find((loc) => fs.existsSync(loc)) || null;
    }

    private getTestSuiteLocations(workspaceRoot: string, promptFile: string): string[] {
        return [
            path.join(path.dirname(promptFile), 'promptci.yaml'),
            path.join(workspaceRoot, '.promptci', 'promptci.yaml'),
            path.join(workspaceRoot, 'promptci.yaml'),
        ];
    }

    private matchesPromptFile(uri: vscode.Uri): boolean {
        const config = vscode.workspace.getConfiguration('promptci');
        const patterns = config.get<string[]>(
            'promptFilePatterns',
            ['**/*.prompt', '**/prompts/**/*.txt', '**/system_prompt.txt']
        );
        const promptPatterns = patterns.filter((p) => !p.includes('promptci.yaml'));
        const relativePath = vscode.workspace.asRelativePath(uri, false);
        return promptPatterns.some((pattern) => this.matchesGlob(relativePath, pattern));
    }

    private matchesGlob(filePath: string, pattern: string): boolean {
        const normalizedPath = filePath.replace(/\\/g, '/');
        const escaped = pattern
            .replace(/[.+^${}()|[\]\\]/g, '\\$&')
            .replace(/\*\*/g, '::DOUBLE_STAR::')
            .replace(/\*/g, '[^/]*')
            .replace(/::DOUBLE_STAR::/g, '.*')
            .replace(/\?/g, '.');
        return new RegExp(`^${escaped}$`).test(normalizedPath);
    }

    private parseYaml(filePath: string): any {
        try {
            return yaml.load(fs.readFileSync(filePath, 'utf8'));
        } catch (error) {
            vscode.window.showErrorMessage(`PromptCI: Invalid YAML in ${filePath}`);
            return null;
        }
    }
}

function outputMessage(message: string, show: boolean = false): void {
    const channel = vscode.window.createOutputChannel('PromptCI');
    if (message) {
        channel.appendLine(message);
    }
    if (show) {
        channel.show(true);
    }
}
