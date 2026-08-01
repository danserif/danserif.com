// Site initialisation (DOM-ready)
(function () {
	function init() {
		var root = document.documentElement;

		function syncThemeColorMeta() {
			var meta = document.querySelector('meta[name="theme-color"]');
			if (!meta) return;
			meta.setAttribute("content", root.classList.contains("light-mode") ? "#ffffff" : "#000000");
		}

		function colorKeyboardTargetOk() {
			var el = document.activeElement;
			if (!el || el === document.body) return true;
			var tag = el.tagName && el.tagName.toLowerCase();
			if (tag === "input" || tag === "textarea" || tag === "select") return false;
			if (el.isContentEditable) return false;
			return true;
		}

		function setMode(mode) {
			if (mode === "light") {
				root.classList.add("light-mode");
			} else {
				root.classList.remove("light-mode");
			}
			try {
				localStorage.setItem("colorMode", mode);
			} catch (e) {}
			syncThemeColorMeta();
		}

		syncThemeColorMeta();

		document.addEventListener("click", function (e) {
			var t = e.target;
			if (!t) return;
			if (t.closest && t.closest(".dark-mode-toggle")) {
				e.preventDefault();
				setMode("dark");
			} else if (t.closest && t.closest(".light-mode-toggle")) {
				e.preventDefault();
				setMode("light");
			}
		});

		/* M key: toggle dark ↔ light */
		document.addEventListener("keydown", function (e) {
			if ((e.key !== "m" && e.key !== "M") || e.repeat || e.ctrlKey || e.metaKey || e.altKey) {
				return;
			}
			if (!colorKeyboardTargetOk()) return;
			e.preventDefault();
			setMode(root.classList.contains("light-mode") ? "dark" : "light");
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
