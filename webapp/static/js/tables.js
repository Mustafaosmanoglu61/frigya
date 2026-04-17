/* Table sorting utilities */

const TABLE_STATE = {};

function initTableSort(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const headers = table.querySelectorAll('th');
    headers.forEach((th, idx) => {
        th.style.cursor = 'pointer';
        th.title = 'Çift tıkla sırala';

        let clicks = 0;
        th.addEventListener('dblclick', () => {
            clicks++;
            const dir = clicks % 2 === 1 ? 'asc' : 'desc';
            sortTable(tableId, idx, dir);

            // Reset other columns
            headers.forEach((other, i) => {
                if (i !== idx) {
                    other.classList.remove('sorted-asc', 'sorted-desc');
                }
            });

            th.classList.toggle('sorted-asc', dir === 'asc');
            th.classList.toggle('sorted-desc', dir === 'desc');
        });
    });
}

function sortTable(tableId, colIdx, direction) {
    const table = document.getElementById(tableId);
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aVal = a.cells[colIdx]?.textContent.trim() || '';
        const bVal = b.cells[colIdx]?.textContent.trim() || '';

        // Try numeric
        const aNum = parseFloat(aVal.replace(/[^\d.-]/g, ''));
        const bNum = parseFloat(bVal.replace(/[^\d.-]/g, ''));

        let result;
        if (!isNaN(aNum) && !isNaN(bNum)) {
            result = aNum - bNum;
        } else {
            result = aVal.localeCompare(bVal, 'tr');
        }

        return direction === 'asc' ? result : -result;
    });

    rows.forEach(row => tbody.appendChild(row));
}

// Style for sorted columns
const style = document.createElement('style');
style.textContent = `
    th.sorted-asc::after  { content: ' ▲'; }
    th.sorted-desc::after { content: ' ▼'; }
`;
document.head.appendChild(style);
