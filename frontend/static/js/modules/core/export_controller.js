import { apiFetch } from './api_client.js';

function getFilenameFromHeaders(headers) {
    const disposition = headers?.get?.('content-disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    return match?.[1];
}

function downloadBlobFile(filename, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function responseErrorMessage(response) {
    const payload = await response.json().catch(() => ({}));
    return payload.message || payload.error || `HTTP ${response.status}`;
}

export async function exportExcelReport() {
    try {
        const response = await apiFetch('/api/export/excel?profile=field', { method: 'GET' }, 15000);
        if (!response.ok) throw new Error(await responseErrorMessage(response));
        const blob = await response.blob();
        const filename = getFilenameFromHeaders(response.headers) || 'smart-chess-field-report.xlsx';
        downloadBlobFile(filename, blob);
        window.showAlert?.('現場 Excel 報告已匯出。', 'success');
    } catch (error) {
        window.showAlert?.(`Excel 匯出失敗：${error.message}`, 'error');
    }
}

export async function exportCsvReport() {
    try {
        const response = await apiFetch('/api/export/csv', { method: 'GET' }, 15000);
        if (!response.ok) throw new Error(await responseErrorMessage(response));
        const blob = await response.blob();
        const filename = getFilenameFromHeaders(response.headers) || 'smart-chess-engineering-events.csv';
        downloadBlobFile(filename, blob);
        window.showAlert?.('工程事件 CSV 已匯出。', 'success');
    } catch (error) {
        window.showAlert?.(`CSV 匯出失敗：${error.message}`, 'error');
    }
}

export async function exportReplayJson(sessionId = null) {
    try {
        const query = sessionId === null || sessionId === undefined
            ? ''
            : `?session=${encodeURIComponent(String(sessionId))}`;
        const response = await apiFetch(`/api/replay/export${query}`, { method: 'GET' }, 15000);
        if (!response.ok) throw new Error(await responseErrorMessage(response));
        const blob = await response.blob();
        const filename = getFilenameFromHeaders(response.headers) || 'smart-chess-replay.json';
        downloadBlobFile(filename, blob);
        window.showAlert?.('回放 JSON 已匯出。', 'success');
    } catch (error) {
        window.showAlert?.(`回放匯出失敗：${error.message}`, 'error');
    }
}
