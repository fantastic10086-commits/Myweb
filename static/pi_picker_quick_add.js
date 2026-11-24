/* Share the existing quick-add dialog without losing the picker selection. */
(function () {
    'use strict';
    var fromPicker = false;
    var createdProduct = null;
    window.PIPickerQuickAdd = {
        added: function (product) { createdProduct = product; }
    };

    document.addEventListener('DOMContentLoaded', function () {
        var picker = document.getElementById('productPickerModal');
        var quickAdd = document.getElementById('quickAddProductModal');
        var button = document.getElementById('picker_quick_add');
        var notice = document.getElementById('product_picker_notice');
        var pickerBody = picker.querySelector('.modal-body');
        var scrollTop = 0;
        var pickerReady = false;

        button.addEventListener('click', function () {
            if (button.disabled || fromPicker || !pickerReady) return;
            if (typeof structuralEditLocked === 'function' && structuralEditLocked()) return;
            if (typeof productEntryReady === 'function' && !productEntryReady()) return;
            fromPicker = true;
            scrollTop = pickerBody.scrollTop;
            picker.addEventListener('hidden.bs.modal', function () {
                bootstrap.Modal.getOrCreateInstance(quickAdd).show();
            }, {once: true});
            bootstrap.Modal.getOrCreateInstance(picker).hide();
        });

        picker.addEventListener('show.bs.modal', function () {
            pickerReady = false;
            if (!fromPicker) notice.classList.add('d-none');
        });
        picker.addEventListener('shown.bs.modal', function () { pickerReady = true; });
        picker.addEventListener('hide.bs.modal', function () { pickerReady = false; });
        quickAdd.addEventListener('show.bs.modal', function () {
            createdProduct = null;
        });
        quickAdd.addEventListener('hide.bs.modal', function (event) {
            // Keep an in-flight save tied to this dialog until it finishes.
            var submit = quickAdd.querySelector('.modal-footer .btn-success');
            if (submit.disabled && !createdProduct) event.preventDefault();
        });
        quickAdd.addEventListener('hidden.bs.modal', function () {
            if (!fromPicker) return;
            var created = createdProduct;
            if (created) {
                notice.textContent = '已新增并加入当前 PI：' + created.name;
                notice.classList.remove('d-none');
            }
            picker.addEventListener('shown.bs.modal', function () {
                fromPicker = false;
                pickerBody.scrollTop = scrollTop;
                if (created) {
                    loadPickerProducts(pickerPage).then(function () {
                        pickerBody.scrollTop = scrollTop;
                    });
                }
            }, {once: true});
            // Do not use openProductPicker(): it resets search, page and selection.
            bootstrap.Modal.getOrCreateInstance(picker).show();
        });
    });
})();
