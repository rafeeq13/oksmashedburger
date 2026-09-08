(function () {
  var docClickBound = false;
  var scrollY = 0;

  function staffModal() {
    return document.getElementById("staffAccessModal");
  }

  function lockPage() {
    scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    document.documentElement.classList.add("staff-modal-open");
    document.body.classList.add("staff-modal-open");
    document.body.style.top = "-" + scrollY + "px";
  }

  function unlockPage() {
    document.documentElement.classList.remove("staff-modal-open");
    document.body.classList.remove("staff-modal-open");
    document.body.style.top = "";
    window.scrollTo(0, scrollY);
  }

  function showStaffModal(modal, open) {
    if (!modal) return;
    if (open) {
      modal.removeAttribute("hidden");
      if (window.OK && typeof window.OK.showModal === "function") {
        window.OK.showModal(modal, null, true);
      } else {
        modal.style.visibility = "visible";
        modal.style.opacity = "1";
        modal.style.pointerEvents = "auto";
        modal.classList.add("is-open");
      }
      return;
    }
    if (window.OK && typeof window.OK.showModal === "function") {
      window.OK.showModal(modal, null, false);
    } else {
      modal.classList.remove("is-open");
      modal.style.opacity = "0";
      modal.style.pointerEvents = "none";
      modal.style.visibility = "hidden";
    }
    modal.setAttribute("hidden", "");
  }

  function openStaffAccess(btn) {
    var modal = staffModal();
    if (!modal || !btn) return;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    var id = btn.getAttribute("data-staff-access-open");
    modal.querySelectorAll(".staff-access-panel").forEach(function (p) {
      p.hidden = p.getAttribute("data-staff-id") !== String(id);
    });
    var subtitle = document.getElementById("staffAccessSubtitle");
    if (subtitle) subtitle.textContent = btn.getAttribute("data-staff-name") || "";
    showStaffModal(modal, true);
    lockPage();
  }

  function closeStaffAccess() {
    var modal = staffModal();
    if (!modal) return;
    showStaffModal(modal, false);
    unlockPage();
  }

  function bindModalChrome(modal) {
    if (!modal || modal._staffChromeBound) return;
    modal._staffChromeBound = true;
    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeStaffAccess();
    });
    var closeBtn = document.getElementById("staffAccessClose");
    if (closeBtn) closeBtn.addEventListener("click", closeStaffAccess);
    modal.addEventListener("touchmove", function (e) {
      var body = modal.querySelector(".staff-access-body");
      if (body && body.contains(e.target)) return;
      e.preventDefault();
    }, { passive: false });
  }

  function boot() {
    var inMain = document.querySelector("main #staffAccessModal");
    var onBody = document.querySelector("body > #staffAccessModal");
    if (inMain && onBody && inMain !== onBody) onBody.remove();
    var modal = inMain || onBody;
    if (!modal) return;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    bindModalChrome(modal);
    if (!docClickBound) {
      docClickBound = true;
      document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-staff-access-open]");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        openStaffAccess(btn);
      });
    }
  }

  window.openStaffAccess = openStaffAccess;
  window.closeStaffAccess = closeStaffAccess;

  document.addEventListener("DOMContentLoaded", boot);
  document.addEventListener("pjax:complete", boot);
  if (document.readyState !== "loading") boot();
})();
