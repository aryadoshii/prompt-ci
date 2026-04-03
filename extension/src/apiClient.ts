import axios from 'axios';

export class ApiClient {
    constructor(private baseUrl: string) {}

    async startRun(payload: {
        prompt_v1: string;
        prompt_v2: string;
        prompt_file: string;
        test_suite: any;
        repo_path: string;
        notify_email: string;
    }): Promise<{ run_id: string; status: string }> {
        const response = await axios.post(`${this.baseUrl}/api/run`, payload);
        return response.data;
    }

    async getRun(runId: string): Promise<any> {
        const response = await axios.get(`${this.baseUrl}/api/run/${runId}`);
        return response.data;
    }

    async getReport(runId: string): Promise<string> {
        const response = await axios.get(`${this.baseUrl}/api/run/${runId}/report`);
        return response.data.html;
    }

    async submitApproval(
        runId: string,
        action: 'approve' | 'dismiss'
    ): Promise<{ success: boolean; branch: string; error: string }> {
        const response = await axios.post(
            `${this.baseUrl}/api/run/${runId}/approve`,
            { action }
        );
        return response.data;
    }

    async getRecentRuns(): Promise<any[]> {
        const response = await axios.get(`${this.baseUrl}/api/runs`);
        return response.data;
    }

    async getStats(): Promise<any> {
        const response = await axios.get(`${this.baseUrl}/api/stats`);
        return response.data;
    }

    async checkHealth(): Promise<any> {
        const response = await axios.get(`${this.baseUrl}/api/health`);
        return response.data;
    }
}
