package main

// desktopDragRegionClass must stay in sync with dashboard DESKTOP_DRAG_REGION_CLASS.
// Frameless moving uses CSS `--wails-draggable: drag` plus this injected starter:
// the remote dashboard origin never loads Wails `/wails/runtime.js`.
// clientY <= 32 must match dashboard DESKTOP_TITLEBAR_DRAG_HEIGHT.
const desktopDragRegionClass = "octop-desktop-drag"

func dragOverlayJS() string {
	return `(function(){
		if (!document.body || !window._wails || typeof window._wails.invoke !== 'function') return;
		if (document.documentElement.dataset.octopDragReady === '1') return;
		document.documentElement.dataset.octopDragReady = '1';
		var armed = false, startX = 0, startY = 0;
		var noDrag = 'button, a, input, textarea, select, [role="button"], [role="menuitem"], [data-octop-no-drag], .octop-desktop-no-drag';
		function targetEl(t) {
			if (t && t.nodeType === 1) return t;
			return t && t.parentElement ? t.parentElement : null;
		}
		function shouldArm(event) {
			if (event.button !== 0) return false;
			var el = targetEl(event.target);
			if (!el || !el.closest) return false;
			if (el.closest(noDrag)) return false;
			var value = window.getComputedStyle(el).getPropertyValue('--wails-draggable').trim();
			if (value === 'no-drag') return false;
			if (value === 'drag') return true;
			return event.clientY <= 32;
		}
		window.addEventListener('mousedown', function(event) {
			if (!shouldArm(event)) return;
			armed = true;
			startX = event.screenX;
			startY = event.screenY;
		}, true);
		window.addEventListener('mousemove', function(event) {
			if (!armed) return;
			if (Math.abs(event.screenX - startX) < 3 && Math.abs(event.screenY - startY) < 3) return;
			armed = false;
			window._wails.invoke('wails:drag');
		}, true);
		window.addEventListener('mouseup', function() { armed = false; }, true);
		window.addEventListener('dblclick', function(event) {
			if (!shouldArm(event)) return;
			window._wails.invoke('wails:drag:doubleclick');
		}, true);
	})();`
}
