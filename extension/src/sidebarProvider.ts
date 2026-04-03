import * as vscode from 'vscode';
import { ApiClient } from './apiClient';

export class SidebarProvider implements vscode.TreeDataProvider<SidebarItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void | SidebarItem | SidebarItem[]>();
    onDidChangeTreeData = this._onDidChangeTreeData.event;
    
    private currentRun: any = null;
    private isRunning: boolean = false;

    constructor(
        private context: vscode.ExtensionContext,
        private apiClient: ApiClient
    ) {}

    setRunning(running: boolean): void {
        this.isRunning = running;
        this._onDidChangeTreeData.fire();
    }

    updateResults(run: any): void {
        this.currentRun = run;
        this._onDidChangeTreeData.fire();
    }

    openReport(runId: string): void {
        // Open HTML report in a VS Code WebviewPanel
        const panel = vscode.window.createWebviewPanel(
            'promptciReport',
            `PromptCI Report — ${runId.substring(0, 8)}`,
            vscode.ViewColumn.Beside,
            { enableScripts: true }
        );
        this.apiClient.getReport(runId).then(html => {
            panel.webview.html = html;
        });
    }

    getTreeItem(element: SidebarItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: SidebarItem): SidebarItem[] {
        if (this.isRunning) {
            return [new SidebarItem('⟳ Running tests...', 'running', vscode.TreeItemCollapsibleState.None)];
        }
        if (!this.currentRun) {
            return [new SidebarItem('No runs yet. Save a prompt file.', 'empty', vscode.TreeItemCollapsibleState.None)];
        }
        
        const run = this.currentRun;
        const passLabel = `${run.passed}/${run.total} tests passed (${Math.round(run.pass_rate)}%)`;
        const testType = run.regressions > 0 || run.failures > 0 || run.errors > 0 ? 'regression' : 'pass';
        
        return [
            new SidebarItem(
                passLabel,
                testType,
                vscode.TreeItemCollapsibleState.None
            ),
            new SidebarItem(`${run.regressions} regression(s)`, 'detail', vscode.TreeItemCollapsibleState.None),
            new SidebarItem(`${run.improvements} improvement(s)`, 'detail', vscode.TreeItemCollapsibleState.None),
            new SidebarItem(`${run.failures || 0} failure(s)`, 'detail', vscode.TreeItemCollapsibleState.None),
            new SidebarItem(`${run.errors || 0} error(s)`, 'detail', vscode.TreeItemCollapsibleState.None),
            new SidebarItem(`Fix: ${run.fix_status}`, 'detail', vscode.TreeItemCollapsibleState.None),
        ];
    }
}

class SidebarItem extends vscode.TreeItem {
    constructor(
        public readonly label: string, 
        public readonly type: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(label, collapsibleState);
        this.contextValue = type;
        if (type === 'pass') {
            this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('testing.iconPassed'));
        } else if (type === 'regression') {
            this.iconPath = new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
        } else if (type === 'running') {
            this.iconPath = new vscode.ThemeIcon('sync~spin');
        } else if (type === 'detail') {
            this.iconPath = new vscode.ThemeIcon('info');
        }
    }
}
