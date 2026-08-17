/* receipt_form.js - Logic for the receipt entry form */

let debounceTimer;
let currentBills = [];
let partyBalance = 0;

document.addEventListener('DOMContentLoaded', () => {
    
    // Elements
    const partySearch = document.getElementById('partySearch');
    const partyCode = document.getElementById('partyCode');
    const partyDropdown = document.getElementById('partyDropdown');
    const amountInput = document.getElementById('amount');
    const cbSelect = document.getElementById('cashBankCode');
    const dateInput = document.getElementById('date');
    if (dateInput && !dateInput.value) {
        const todayStr = new Date().toISOString().split('T')[0];
        dateInput.value = todayStr;
    }
    
    let selectedIndex = -1;

    function updateSelection(items) {
        items.forEach((item, index) => {
            if (index === selectedIndex) {
                item.classList.add('active');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('active');
            }
        });
    }

    // Event Listeners
    partySearch.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const q = e.target.value.trim();
        selectedIndex = -1;
        
        if (!q) {
            partyDropdown.classList.add('hidden');
            return;
        }
        
        debounceTimer = setTimeout(() => searchParties(q), 300);
    });

    partySearch.addEventListener('keydown', (e) => {
        const items = partyDropdown.querySelectorAll('.dropdown-item');
        if (partyDropdown.classList.contains('hidden') || items.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (selectedIndex < items.length - 1) {
                selectedIndex++;
            } else {
                selectedIndex = 0;
            }
            updateSelection(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (selectedIndex > 0) {
                selectedIndex--;
            } else {
                selectedIndex = items.length - 1;
            }
            updateSelection(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIndex >= 0 && selectedIndex < items.length) {
                items[selectedIndex].click();
            } else if (items.length > 0 && !items[0].textContent.includes('No parties found')) {
                items[0].click();
            }
        } else if (e.key === 'Escape') {
            partyDropdown.classList.add('hidden');
            selectedIndex = -1;
        }
    });
    
    // Hide dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!partySearch.contains(e.target) && !partyDropdown.contains(e.target)) {
            partyDropdown.classList.add('hidden');
            selectedIndex = -1;
        }
    });

    amountInput.addEventListener('input', updateSummary);
    cbSelect.addEventListener('change', updateSummary);
    dateInput.addEventListener('change', updateSummary);

    // Form submit
    document.getElementById('receiptForm').addEventListener('submit', submitReceipt);
    document.getElementById('clearBtn').addEventListener('click', () => location.reload());

    async function searchParties(query) {
        try {
            const res = await fetch(`/api/parties?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            const dd = document.getElementById('partyDropdown');
            dd.innerHTML = '';
            selectedIndex = -1;
            
            if (data.length === 0) {
                dd.innerHTML = '<div class="dropdown-item"><span class="item-name text-muted">No parties found</span></div>';
            } else {
                data.forEach((p, idx) => {
                    const div = document.createElement('div');
                    div.className = 'dropdown-item';
                    div.innerHTML = `<div class="item-name">${p.name}</div><div class="item-group">${p.group}</div>`;
                    div.addEventListener('click', () => selectParty(p.code, p.name));
                    div.addEventListener('mouseenter', () => {
                        selectedIndex = idx;
                        updateSelection(dd.querySelectorAll('.dropdown-item'));
                    });
                    dd.appendChild(div);
                });
            }
            dd.classList.remove('hidden');
        } catch (e) {
            console.error('Error searching parties:', e);
        }
    }

async function selectParty(code, name) {
    document.getElementById('partyCode').value = code;
    document.getElementById('partySearch').value = name;
    document.getElementById('partyDropdown').classList.add('hidden');
    document.getElementById('summParty').textContent = name;
    
    // Fetch balance and bills
    fetchBalance(code);
    fetchBills(code);
    updateSummary();
}

async function fetchBalance(code) {
    try {
        const res = await fetch(`/api/party/${code}/balance`);
        const data = await res.json();
        
        const balDiv = document.getElementById('partyBalance');
        const valSpan = document.getElementById('balanceValue');
        
        valSpan.textContent = fmtCurrency(data.amount) + ' ' + data.dr_cr;
        valSpan.className = 'balance-amount ' + (data.dr_cr === 'Dr' ? 'balance-dr' : 'balance-cr');
        balDiv.classList.remove('hidden');
        partyBalance = (data.dr_cr === 'Dr' ? -data.amount : data.amount);
    } catch (e) {
        console.error('Error fetching balance:', e);
    }
}

async function fetchBills(code) {
    try {
        const res = await fetch(`/api/party/${code}/bills`);
        const data = await res.json();
        currentBills = data;
        
        const tbody = document.getElementById('billsTableBody');
        const sec = document.getElementById('billSection');
        
        if (data.length === 0) {
            sec.classList.add('hidden');
            return;
        }
        
        sec.classList.remove('hidden');
        tbody.innerHTML = '';
        
        data.forEach((b, i) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><input type="checkbox" class="checkbox bill-cb" data-idx="${i}"></td>
                <td>${b.bill_no}</td>
                <td>${b.date}</td>
                <td>${b.due_date}</td>
                <td class="text-right">${fmtCurrency(b.original_amount)}</td>
                <td class="text-right">${fmtCurrency(b.balance)}</td>
                <td class="text-right">
                    <input type="number" class="bill-pay-input" data-idx="${i}" 
                           max="${b.balance}" value="0.00" step="0.01" disabled>
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Add event listeners for bills
        document.querySelectorAll('.bill-cb').forEach(cb => {
            cb.addEventListener('change', handleBillCheckbox);
        });
        
        document.querySelectorAll('.bill-pay-input').forEach(inp => {
            inp.addEventListener('input', calculateAdjustments);
        });
        
        document.getElementById('selectAllBills').addEventListener('change', (e) => {
            const checked = e.target.checked;
            document.querySelectorAll('.bill-cb').forEach(cb => {
                cb.checked = checked;
                handleBillCheckbox({ target: cb });
            });
        });
        
    } catch (e) {
        console.error('Error fetching bills:', e);
    }
}

function handleBillCheckbox(e) {
    const idx = e.target.dataset.idx;
    const inp = document.querySelector(`.bill-pay-input[data-idx="${idx}"]`);
    
    if (e.target.checked) {
        inp.disabled = false;
        // Auto fill remaining amount up to bill balance
        const currentTotal = parseFloat(document.getElementById('amount').value || 0);
        const adjTotal = getAdjustedTotal();
        const rem = Math.max(0, currentTotal - adjTotal);
        const maxPay = currentBills[idx].balance;
        
        inp.value = Math.min(rem, maxPay).toFixed(2);
    } else {
        inp.disabled = true;
        inp.value = '0.00';
    }
    calculateAdjustments();
}

function getAdjustedTotal() {
    let tot = 0;
    document.querySelectorAll('.bill-pay-input:not(:disabled)').forEach(inp => {
        tot += parseFloat(inp.value || 0);
    });
    return tot;
}

function calculateAdjustments() {
    const adjTotal = getAdjustedTotal();
    const currentTotal = parseFloat(document.getElementById('amount').value || 0);
    const rem = currentTotal - adjTotal;
    
    document.getElementById('totalAdjusted').textContent = fmtCurrency(adjTotal);
    const remEl = document.getElementById('remainingAmount');
    remEl.textContent = fmtCurrency(Math.max(0, rem));
    
    if (rem < 0) {
        remEl.style.color = '#ff6b6b';
        remEl.textContent = 'Exceeded by ' + fmtCurrency(Math.abs(rem));
    } else {
        remEl.style.color = 'var(--accent-cyan)';
    }
}

function updateSummary() {
    const amt = parseFloat(document.getElementById('amount').value || 0);
    const cb = document.getElementById('cashBankCode');
    const dt = document.getElementById('date').value;
    
    document.getElementById('summDr').textContent = fmtCurrency(amt);
    document.getElementById('summCr').textContent = fmtCurrency(amt);
    document.getElementById('summTotal').textContent = fmtCurrency(amt);
    
    if (cb.selectedIndex > 0) {
        const summBankEl = document.getElementById('summBank');
        if (summBankEl) summBankEl.textContent = cb.options[cb.selectedIndex].text;
    }
    if (dt) document.getElementById('summDate').textContent = dt;
    
    calculateAdjustments(); // Update bill remaining amount based on new total
}

async function submitReceipt(e) {
    e.preventDefault();
    
    const form = e.target;
    if (!form.checkValidity()) {
        form.classList.add('was-validated');
        showToast('Please fill all required fields correctly', 'error');
        return;
    }
    
    const amount = parseFloat(document.getElementById('amount').value);
    if (amount <= 0) {
        showToast('Amount must be greater than 0', 'error');
        return;
    }
    
    const adjTotal = getAdjustedTotal();
    if (adjTotal > amount + 0.01) { // Adding small delta for float precision
        showToast('Bill adjustments cannot exceed total amount', 'error');
        return;
    }

    // Build adjustments array
    const adjs = [];
    document.querySelectorAll('.bill-pay-input:not(:disabled)').forEach(inp => {
        const val = parseFloat(inp.value || 0);
        if (val > 0) {
            const idx = inp.dataset.idx;
            adjs.push({
                ref_code: currentBills[idx].ref_code,
                amount: val
            });
        }
    });

    const data = {
        party_code: document.getElementById('partyCode').value,
        cash_bank_code: document.getElementById('cashBankCode').value,
        amount: amount,
        date: document.getElementById('date').value,
        narration: document.getElementById('narration').value,
        bill_adjustments: adjs
    };

    // UI state
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    const btnText = btn.querySelector('.btn-text');
    const btnSpinner = btn.querySelector('.btn-spinner');
    if (btnText) btnText.classList.add('hidden');
    if (btnSpinner) btnSpinner.classList.remove('hidden');

    try {
        const res = await fetch('/api/receipt/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await res.json();
        
        if (!res.ok || result.error) {
            throw new Error(result.error || 'Server error');
        }
        
        // Success! Show modal
        lastSavedVchNo = result.vch_no;
        const modalVchNo = document.getElementById('modalVchNo');
        const modalOverlay = document.getElementById('modalOverlay');
        const successModal = document.getElementById('successModal');
        
        if (modalVchNo && modalOverlay && successModal) {
            modalVchNo.textContent = 'Voucher No: ' + result.vch_no;
            modalOverlay.classList.remove('hidden');
            successModal.classList.remove('hidden');
        } else {
            // Fallback if modal elements don't exist
            showToast('Receipt saved successfully! Voucher No: ' + result.vch_no, 'success');
            setTimeout(() => location.reload(), 2000);
        }
        
    } catch (err) {
        console.error(err);
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
        if (btnText) btnText.classList.remove('hidden');
        if (btnSpinner) btnSpinner.classList.add('hidden');
    }
}

let lastSavedVchNo = "";

function closeModal() {
    document.getElementById('modalOverlay').classList.add('hidden');
    document.getElementById('successModal').classList.add('hidden');
}

function closeModalAndNew() {
    closeModal();
    location.reload();
}

function printReceipt() {
    if (lastSavedVchNo) {
        window.open('/print/receipt/' + lastSavedVchNo, '_blank', 'width=600,height=800');
    }
}

}); // Close DOMContentLoaded
