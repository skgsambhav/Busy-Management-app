/* app.js - General utilities */

// Toast notification
function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast toast-${type} show`;
  setTimeout(() => { t.className = 'toast'; }, 4000);
}

// Format currency
function fmtCurrency(val) {
  return '₹' + parseFloat(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Toggle Nav Group
function toggleNavGroup(element) {
  const group = element.closest('.nav-group');
  if (!group) return;

  // Close other groups except the active route group
  document.querySelectorAll('.sidebar-nav .nav-group').forEach(g => {
    if (g !== group && !g.querySelector('.nav-item.active')) {
      g.classList.remove('open');
    }
  });

  group.classList.toggle('open');
}
