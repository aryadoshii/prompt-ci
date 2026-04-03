import { exec, execFile } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

export class GitClient {
    
    async getHeadVersion(repoPath: string, filePath: string): Promise<string | null> {
        // Get the HEAD version of a file via git show HEAD
        try {
            // Get relative path from repo root
            const { stdout: relPath } = await execAsync(
                `git -C "${repoPath}" ls-files --full-name "${filePath}"`
            );
            const relativePath = relPath.trim();
            if (!relativePath) return null;
            
            const { stdout } = await execAsync(
                `git -C "${repoPath}" show HEAD:"${relativePath}"`
            );
            return stdout;
        } catch {
            return null;   // file not tracked or no commits yet
        }
    }

    async createBranchAndCommit(
        repoPath: string,
        branchName: string,
        filePath: string,
        commitMessage: string,
    ): Promise<{ success: boolean; error: string }> {
        try {
            await execAsync(`git -C "${repoPath}" checkout -b "${branchName}"`);
            await execAsync(`git -C "${repoPath}" add "${filePath}"`);
            await execAsync(
                `git -C "${repoPath}" commit -m "${commitMessage}"`
            );
            await execAsync(
                `git -C "${repoPath}" push origin "${branchName}"`
            );
            return { success: true, error: '' };
        } catch (err: any) {
            return { success: false, error: err.message };
        }
    }

    async getCurrentBranch(repoPath: string): Promise<string> {
        const { stdout } = await execAsync(
            `git -C "${repoPath}" rev-parse --abbrev-ref HEAD`
        );
        return stdout.trim();
    }

    async hasUncommittedChanges(repoPath: string, filePath: string): Promise<boolean> {
        const { stdout } = await execAsync(
            `git -C "${repoPath}" status --porcelain "${filePath}"`
        );
        return stdout.trim().length > 0;
    }

    async isTracked(repoPath: string, filePath: string): Promise<boolean> {
        try {
            const { stdout } = await execAsync(
                `git -C "${repoPath}" ls-files --full-name "${filePath}"`
            );
            return stdout.trim().length > 0;
        } catch {
            return false;
        }
    }

    async cloneRepository(repoUrl: string, parentDir: string): Promise<{ success: boolean; repoPath: string; error: string }> {
        try {
            const repoName = this.getRepoNameFromUrl(repoUrl);
            const repoPath = path.join(parentDir, repoName);

            await execFileAsync('git', ['clone', repoUrl, repoPath]);
            return { success: true, repoPath, error: '' };
        } catch (err: any) {
            return {
                success: false,
                repoPath: '',
                error: err.stderr || err.message || 'Failed to clone repository',
            };
        }
    }

    private getRepoNameFromUrl(repoUrl: string): string {
        const normalized = repoUrl.trim().replace(/\/+$/, '');
        const lastSegment = normalized.split('/').pop() || 'repo';
        return lastSegment.endsWith('.git') ? lastSegment.slice(0, -4) : lastSegment;
    }
}
