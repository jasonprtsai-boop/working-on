import { apiFetch } from './api_client.js';

function formatJsonText(text) {
    try {
        return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
        return text;
    }
}

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

function downloadTextFile(filename, content, type) {
    downloadBlobFile(filename, new Blob([content], { type }));
}

export async function exportJsonRecord() {
    try {
        const response = await apiFetch('/api/export_json', { method: 'GET' }, 10000);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const text = await response.text();
        downloadTextFile('smart-chess-record.json', formatJsonText(text), 'application/json');
        window.showAlert?.('Record exported.', 'success');
    } catch (error) {
        window.showAlert?.(`Record export failed: ${error.message}`, 'error');
    }
}

export async function exportExcelReport() {
    try {
        const response = await apiFetch('/api/export/excel', { method: 'GET' }, 15000);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        const filename = getFilenameFromHeaders(response.headers) || 'smart-chess-report.xlsx';
        downloadBlobFile(filename, blob);
        window.showAlert?.('Excel report exported.', 'success');
    } catch (error) {
        window.showAlert?.(`Excel export failed: ${error.message}`, 'error');
    }
}

export async function exportCsvReport() {
    try {
        const response = await apiFetch('/api/export/csv', { method: 'GET' }, 15000);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        const filename = getFilenameFromHeaders(response.headers) || 'smart-chess-events.csv';
        downloadBlobFile(filename, blob);
        window.showAlert?.('CSV event log exported.', 'success');
    } catch (error) {
        window.showAlert?.(`CSV export failed: ${error.message}`, 'error');
    }
}

export function exportVisibleLogs() {
    const logs = document.getElementById('admin-logs');
    const text = logs?.innerText || logs?.textContent || 'No logs captured.';
    downloadTextFile('smart-chess-console.log', text, 'text/plain');
    window.showAlert?.('Console log exported.', 'success');
}
