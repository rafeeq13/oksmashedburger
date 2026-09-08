/** Live Uber / order status updates on admin orders list + order detail. */
(function () {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusBadge(status) {
    if (status === "completed") {
      return '<span class="badge badge-green">Completed</span>';
    }
    if (status === "cancelled") {
      return '<span class="badge badge-red">Cancelled</span>';
    }
    return '<span class="badge badge-yellow text-capitalize">' + esc(status.replace(/_/g, " ")) + "</span>";
  }

  function deliveryHint(delivery) {
    if (!delivery || delivery.method !== "uber_direct") return "";
    var st = delivery.status || "";
    if (st === "assigned") {
      return ' <span class="ok-fs-xs text-ok-green fw-semibold">· Rider assigned</span>';
    }
    if (st === "picked_up") {
      return ' <span class="ok-fs-xs text-ok-green fw-semibold">· On the way</span>';
    }
    return "";
  }

  function pollDetail() {
    var root = document.querySelector("[data-admin-order-detail]");
    if (!root) return;
    var num = root.getAttribute("data-order-number");
    if (!num) return;
    var last = root.getAttribute("data-order-status") || "";
    var lastDel = root.getAttribute("data-delivery-status") || "";

    function tick() {
      fetch("/admin/api/orders/" + encodeURIComponent(num) + "/status", {
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (d) {
          if (!d) return;
          var delSt = d.delivery ? d.delivery.status || "" : "";
          if (d.status !== last || delSt !== lastDel) {
            window.location.reload();
          }
        })
        .catch(function () {});
    }

    setInterval(tick, 10000);
    tick();
  }

  function pollList() {
    var rows = document.querySelectorAll("[data-admin-order-row]");
    if (!rows.length) return;
    var active = [];
    rows.forEach(function (row) {
      if (row.getAttribute("data-terminal") === "1") return;
      active.push(row.getAttribute("data-order-number"));
    });
    if (!active.length) return;

    function apply(items) {
      (items || []).forEach(function (d) {
        var row = document.querySelector(
          '[data-admin-order-row][data-order-number="' + d.number + '"]'
        );
        if (!row) return;
        var statusCell = row.querySelector("[data-order-status-cell]");
        var typeCell = row.querySelector("[data-order-type-cell]");
        if (statusCell) {
          statusCell.innerHTML = statusBadge(d.status) + deliveryHint(d.delivery);
        }
        row.setAttribute("data-order-status", d.status);
        row.setAttribute(
          "data-delivery-status",
          d.delivery ? d.delivery.status || "" : ""
        );
        if (d.terminal) row.setAttribute("data-terminal", "1");
        if (typeCell && d.delivery && d.delivery.method === "uber_direct") {
          var hint = "";
          if (d.delivery.status === "assigned") hint = " · Rider assigned";
          else if (d.delivery.status === "picked_up") hint = " · En route";
          typeCell.innerHTML =
            'Delivery <span class="ok-fs-xs text-muted-warm ok-normal-case">(Uber' +
            esc(hint) +
            ")</span>";
        }
      });
    }

    function tick() {
      var qs =
        "numbers=" +
        encodeURIComponent(
          active.filter(function (n, i, a) {
            return a.indexOf(n) === i;
          }).join(",")
        );
      fetch("/admin/api/orders/status?" + qs, { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(apply)
        .catch(function () {});
    }

    setInterval(tick, 15000);
    tick();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      pollDetail();
      pollList();
    });
  } else {
    pollDetail();
    pollList();
  }
})();
