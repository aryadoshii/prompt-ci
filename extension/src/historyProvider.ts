import * as vscode from 'vscode';
import { ApiClient } from './apiClient';

export class HistoryProvider implements vscode.TreeDataProvider<HistoryItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void | HistoryItem | HistoryItem[]>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private runs: any[] = [];

    constructor(private apiClient: ApiClient) {}

    async refresh(): Promise<void> {
        try {
            this.runs = await this.apiClient.getRecentRuns();
        } catch {
            this.runs = [];
        }
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: HistoryItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<HistoryItem[]> {
        if (this.runs.length === 0) {
            await this.refresh();
        }

        if (this.runs.length === 0) {
            return [new HistoryItem('No completed runs yet.', '', '')];
        }

        return this.runs.slice(0, 10).map((run) => {
            const statusBits = [
                `${run.passed || 0}/${run.total_tests || 0} passed`,
                `${run.regressions || 0} regressions`,
                `${run.failures || 0} failures`,
                `${run.errors || 0} errors`,
            ];
            const item = new HistoryItem(
                `${(run.prompt_file || 'prompt').split('/').pop()} • ${run.id.slice(0, 8)}`,
                statusBits.join(' • '),
                run.id,
            );
            item.iconPath = new vscode.ThemeIcon(
                run.regressions > 0 || run.failures > 0 || run.errors > 0 ? 'error' : 'check',
                new vscode.ThemeColor(
                    run.regressions > 0 || run.failures > 0 || run.errors > 0
                        ? 'testing.iconFailed'
                        : 'testing.iconPassed'
                )
            );
            if (run.report_path) {
                item.command = {
                    command: 'promptci.openReport',
                    title: 'Open PromptCI Report',
                    arguments: [run.id],
                };
            }
            return item;
        });
    }
}

class HistoryItem extends vscode.TreeItem {
    constructor(
        label: string,
        description: string,
        public readonly runId: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = description;
        this.contextValue = runId ? 'historyRun' : 'historyEmpty';
    }
}
