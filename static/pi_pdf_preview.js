// Display the same PDF bytes produced by the direct export endpoint.
(function () {
    let revision = 0;
    let objectUrl = null;
    const modal = document.getElementById('piPreviewModal');
    const body = document.getElementById('piPreviewBody');
    function release() {
        body.replaceChildren();
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = null;
    }
    modal.addEventListener('hidden.bs.modal', function () { ++revision; release(); });
    window.previewPI = async function (id) {
        const current = ++revision;
        release();
        body.textContent = '正在生成导出 PDF，请稍候……';
        bootstrap.Modal.getOrCreateInstance(modal).show();
        try {
            const response = await fetch('/pi/' + id + '/download?inline=1', {cache: 'no-store'});
            if (!response.ok || !(response.headers.get('Content-Type') || '').includes('application/pdf')) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || '无法加载 PDF，请确认登录状态后重试。');
            }
            const blob = await response.blob();
            if (current !== revision) return;
            objectUrl = URL.createObjectURL(blob);
            body.replaceChildren();
            const link = document.createElement('a');
            link.href = objectUrl;
            link.target = '_blank';
            link.rel = 'noopener';
            link.className = 'btn btn-sm btn-outline-primary mb-2';
            link.textContent = '在新窗口打开 PDF';
            const frame = document.createElement('iframe');
            frame.title = 'PI 导出 PDF';
            frame.src = objectUrl;
            frame.style.cssText = 'display:block;width:100%;height:75vh;border:0';
            body.append(link, frame);
        } catch (error) {
            if (current === revision) body.textContent = error.message;
        }
    };
})();
