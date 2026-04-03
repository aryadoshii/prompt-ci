import * as vscode from 'vscode';
import * as path from 'path';
import { ApiClient } from './apiClient';
import { SidebarProvider } from './sidebarProvider';

export class NotificationHandler {

    constructor(
        private apiClient: ApiClient,
        private sidebarProvider: SidebarProvider
    ) {}

    async showResult(run: any, promptFile: string): Promise<void> {
        const { passed, regressions, total, has_fix, fix_status, failures = 0, errors = 0 } = run;

        if (errors > 0) {
            const action = await vscode.window.showErrorMessage(
                `❌ PromptCI: ${errors} test error(s) occurred while running ${path.basename(promptFile)}. Check the report for runner/API details.`,
                'View Report',
                'Dismiss'
            );
            if (action === 'View Report') {
                this.sidebarProvider.openReport(run.id);
            }
            return;
        }

        if (regressions === 0 && failures === 0) {
            // All pass
            vscode.window.showInformationMessage(
                `✅ PromptCI: All ${total} tests passed. No regressions detected.`
            );
            return;
        }

        if (regressions === 0 && failures > 0) {
            const action = await vscode.window.showWarningMessage(
                `⚠️ PromptCI: ${failures} test(s) failed for ${path.basename(promptFile)} without a baseline regression. Review the report before shipping.`,
                'View Report',
                'Dismiss'
            );
            if (action === 'View Report') {
                this.sidebarProvider.openReport(run.id);
            }
            return;
        }

        // Regressions found
        if (has_fix && fix_status === 'resolved') {
            // Fix available — show approval dialog
            const action = await vscode.window.showWarningMessage(
                `⚠️ PromptCI: ${regressions} regression(s) found in ${passed}/${total} tests. ` +
                `A fix has been generated. Apply and push to GitHub?`,
                'Apply Fix & Push',
                'View Report',
                'Dismiss'
            );

            if (action === 'Apply Fix & Push') {
                await this.handleApproval(run.id, 'approve');
            } else if (action === 'View Report') {
                this.sidebarProvider.openReport(run.id);
            }
        } else if (fix_status === 'unresolvable') {
            // Can't auto-fix
            const action = await vscode.window.showErrorMessage(
                `❌ PromptCI: ${regressions} regression(s) found. ` +
                `Could not auto-fix. Manual review needed.`,
                'View Report',
                'Dismiss'
            );
            if (action === 'View Report') {
                this.sidebarProvider.openReport(run.id);
            }
        }
    }

    async handleApproval(runId: string, action: 'approve' | 'dismiss'): Promise<void> {
        try {
            const result = await this.apiClient.submitApproval(runId, action);
            
            if (action === 'approve') {
                if (result.success) {
                    const prUrl: string = (result as any).pr_url || '';
                    if (prUrl) {
                        const open = await vscode.window.showInformationMessage(
                            `✅ PromptCI: Fix applied. PR created: ${result.branch}`,
                            'Open PR on GitHub'
                        );
                        if (open === 'Open PR on GitHub') {
                            vscode.env.openExternal(vscode.Uri.parse(prUrl));
                        }
                    } else {
                        vscode.window.showInformationMessage(
                            `✅ PromptCI: Fix applied. Branch pushed: ${result.branch}`
                        );
                    }
                } else {
                    vscode.window.showErrorMessage(
                        `❌ PromptCI: Git push failed: ${result.error}`
                    );
                }
            }
        } catch (err: any) {
            vscode.window.showErrorMessage(`PromptCI API Error: ${err.message}`);
        }
    }
}
