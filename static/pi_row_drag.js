/* Move real rows, keeping their inputs and selected files intact. */
window.PIRowDrag = function (body, changed) {
    var row = null, placeholder = null, pointer = null, frame = null, y = 0;
    function finish() {
        if (!row) return;
        if (placeholder && placeholder.parentNode) placeholder.before(row);
        row.style.display = ''; row.classList.remove('pi-dragging');
        if (placeholder) placeholder.remove();
        row = null; placeholder = null; pointer = null;
        cancelAnimationFrame(frame); changed();
    }
    function place(clientY) {
        var rows = Array.from(body.querySelectorAll('tr')).filter(function (r) { return r !== row && r !== placeholder; });
        var next = rows.find(function (r) { var b = r.getBoundingClientRect(); return clientY < b.top + b.height / 2; });
        if (next) body.insertBefore(placeholder, next); else body.appendChild(placeholder);
    }
    function scroll() {
        if (!row) return;
        if (y < 90) window.scrollBy(0, -12);
        else if (y > window.innerHeight - 90) window.scrollBy(0, 12);
        place(y); frame = requestAnimationFrame(scroll);
    }
    body.addEventListener('pointerdown', function (event) {
        var handle = event.target.closest('.sel-drag');
        if (!handle || event.button !== 0) return;
        event.preventDefault(); pointer = event.pointerId; y = event.clientY;
        row = handle.closest('tr'); placeholder = document.createElement('tr');
        var cell = document.createElement('td'); cell.colSpan = 7;
        cell.style.height = row.getBoundingClientRect().height + 'px';
        cell.style.border = '2px dashed #0d6efd'; cell.style.background = '#eaf3ff';
        placeholder.appendChild(cell); row.before(placeholder); row.style.display = 'none';
        frame = requestAnimationFrame(scroll);
    });
    document.addEventListener('pointermove', function (event) {
        if (!row || event.pointerId !== pointer) return;
        event.preventDefault(); y = event.clientY; place(y);
    }, {passive: false});
    document.addEventListener('pointerup', finish);
    document.addEventListener('pointercancel', finish);
    window.addEventListener('blur', finish);
    body.addEventListener('keydown', function (event) {
        if (!event.target.closest('.sel-drag') || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault(); var current = event.target.closest('tr');
        if (event.key === 'ArrowUp' && current.previousElementSibling) current.previousElementSibling.before(current);
        if (event.key === 'ArrowDown' && current.nextElementSibling) current.nextElementSibling.after(current);
        changed();
    });
};
