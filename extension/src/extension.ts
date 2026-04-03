import * as vscode from 'vscode';
import * as path from 'path';
import { PromptWatcher } from './promptWatcher';
import { ApiClient } from './apiClient';
import { SidebarProvider } from './sidebarProvider';
import { HistoryProvider } from './historyProvider';
import { NotificationHandler } from './notificationHandler';
import { GitClient } from './gitClient';

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel("PromptCI");
    outputChannel.appendLine("PromptCI Extension Activated");
    
    const config = vscode.workspace.getConfiguration('promptci');
    const backendUrl = config.get<string>('backendUrl', 'http://localhost:8000');
    
    const apiClient = new ApiClient(backendUrl);
    const gitClient = new GitClient();
    const sidebarProvider = new SidebarProvider(context, apiClient);
    const historyProvider = new HistoryProvider(apiClient);
    const notificationHandler = new NotificationHandler(apiClient, sidebarProvider);
    const watcher = new PromptWatcher(apiClient, notificationHandler, sidebarProvider, historyProvider);
    
    // Register sidebar views
    vscode.window.registerTreeDataProvider('promptci.results', sidebarProvider);
    vscode.window.registerTreeDataProvider('promptci.history', historyProvider);
    void historyProvider.refresh();
    
    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('promptci.runTests', () => {
            watcher.runManually();
        }),
        vscode.commands.registerCommand('promptci.diagnose', () => {
            watcher.diagnoseSetup();
        }),
        vscode.commands.registerCommand('promptci.approveAndPush', 
            (runId: string) => {
                notificationHandler.handleApproval(runId, 'approve');
            }
        ),
        vscode.commands.registerCommand('promptci.openReport', 
            (runId: string) => {
                sidebarProvider.openReport(runId);
            }
        ),
        vscode.commands.registerCommand('promptci.connectGithubRepo', async () => {
            const repoUrl = await vscode.window.showInputBox({
                prompt: 'Enter the GitHub repository URL to clone',
                placeHolder: 'https://github.com/owner/repo.git',
                ignoreFocusOut: true,
                validateInput: (value) => value.trim() ? undefined : 'Repository URL is required',
            });

            if (!repoUrl) {
                return;
            }

            const targetDir = await vscode.window.showOpenDialog({
                canSelectFiles: false,
                canSelectFolders: true,
                canSelectMany: false,
                openLabel: 'Choose Parent Folder',
                title: 'Select where PromptCI should clone the repository',
                defaultUri: vscode.workspace.workspaceFolders?.[0]?.uri,
            });

            if (!targetDir?.[0]) {
                return;
            }

            await vscode.window.withProgress(
                {
                    location: vscode.ProgressLocation.Notification,
                    title: 'PromptCI: Cloning repository...',
                    cancellable: false,
                },
                async () => {
                    const result = await gitClient.cloneRepository(repoUrl, targetDir[0].fsPath);
                    if (!result.success) {
                        vscode.window.showErrorMessage(`PromptCI: Failed to clone repository. ${result.error}`);
                        return;
                    }

                    const action = await vscode.window.showInformationMessage(
                        `PromptCI: Repository cloned to ${path.basename(result.repoPath)}.`,
                        'Open Cloned Repo'
                    );

                    if (action === 'Open Cloned Repo') {
                        await vscode.commands.executeCommand(
                            'vscode.openFolder',
                            vscode.Uri.file(result.repoPath),
                            true
                        );
                    }
                }
            );
        }),
        vscode.commands.registerCommand('promptci.configure', () => {
             vscode.commands.executeCommand('workbench.action.openSettings', 'promptci');
        })
    );
    
    // Start file watcher if autoRunOnSave is enabled
    if (config.get<boolean>('autoRunOnSave', true)) {
        watcher.start();
        context.subscriptions.push({ dispose: () => watcher.dispose() });
    }
    
    // Show status bar item
    const statusBar = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left
    );
    statusBar.text = '$(beaker) PromptCI';
    statusBar.tooltip = 'PromptCI: Click to run regression tests';
    statusBar.command = 'promptci.runTests';
    statusBar.show();
    context.subscriptions.push(statusBar);
    
    console.log('PromptCI extension loaded and active.');
    outputChannel.appendLine('PromptCI: Loaded and watching for prompt changes.');
    vscode.window.setStatusBarMessage('PromptCI active', 3000);
}

export function deactivate() {
    if (outputChannel) {
        outputChannel.dispose();
    }
}
