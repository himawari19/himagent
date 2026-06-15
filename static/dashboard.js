document.addEventListener("DOMContentLoaded", () => {
  const dashLoading = document.getElementById("dashLoading");
  const dashContent = document.getElementById("dashContent");
  const statCards = document.getElementById("statCards");
  const barChart = document.getElementById("barChart");
  const recentFilesBody = document.getElementById("recentFilesBody");

  // Dynamically create toast container
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.style.cssText =
      "position:fixed;top:20px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:10px;max-width:420px;pointer-events:none;";
    document.body.appendChild(toastContainer);
  }

  const TOAST_ICONS = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };
  const TOAST_TITLES = {
    success: "Success",
    error: "Error",
    warning: "Warning",
    info: "Info",
  };

  function showToast(message, type = "info", duration = 6000) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
            <span class="toast-icon">${TOAST_ICONS[type] || "ℹ️"}</span>
            <div class="toast-body">
                <div class="toast-title">${TOAST_TITLES[type] || type}</div>
                <div class="toast-msg">${message}</div>
            </div>
            <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>`;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("removing");
      toast.addEventListener("animationend", () => toast.remove());
    }, duration);
  }

  // Modal elements
  const previewModal = document.getElementById("previewModal");
  const previewFilename = document.getElementById("previewFilename");
  const previewHeaderIcon = document.getElementById("previewHeaderIcon");
  const previewCopyBtn = document.getElementById("previewCopyBtn");
  const previewSaveBtn = document.getElementById("previewSaveBtn");
  const closePreviewBtn = document.getElementById("closePreviewBtn");
  const excelTabs = document.getElementById("excelTabs");
  const codeViewerContainer = document.getElementById("codeViewerContainer");
  const codeViewer = document.getElementById("codeViewer");
  const excelViewerContainer = document.getElementById("excelViewerContainer");
  const excelTable = document.getElementById("excelTable");

  let currentPreviewContent = "";
  let currentFilename = "";
  let currentSheetsData = null;
  let excelChanges = {}; // { sheetName: [{'coordinate': 'A1', 'value': 'val'}] }

  const previewSubHeader = document.getElementById("previewSubHeader");
  const previewSearchInput = document.getElementById("previewSearchInput");
  const exportToggleBtn = document.getElementById("exportToggleBtn");
  const exportMenu = document.getElementById("exportMenu");

  async function loadStats() {
    try {
      const response = await fetch(`/api/stats?t=${Date.now()}`, {
        cache: "no-store",
      });
      const data = await response.json();

      if (!data.success) {
        console.error("Failed to load dashboard stats:", data.message);
        dashLoading.innerHTML = `<i class="fa-solid fa-circle-exclamation" style="font-size:24px; color:var(--color-danger); margin-bottom:8px; display:block;"></i> Failed to load stats: ${data.message}`;
        return;
      }

      // 1. Render Stat Cards
      statCards.innerHTML = `
                <div class="stat-card">
                    <i class="fa-solid fa-file-excel stat-icon"></i>
                    <div class="stat-value">${data.total_plans}</div>
                    <div class="stat-label">Workbooks Generated</div>
                </div>
                <div class="stat-card">
                    <i class="fa-solid fa-clipboard-list stat-icon"></i>
                    <div class="stat-value">${data.total_test_cases}</div>
                    <div class="stat-label">Total Test Cases</div>
                </div>
                <div class="stat-card">
                    <i class="fa-solid fa-database stat-icon"></i>
                    <div class="stat-value">${data.total_size_kb} KB</div>
                    <div class="stat-label">Storage Used</div>
                </div>
            `;

      // 2. Render Bar Chart with Chart.js
      if (data.chart_labels && data.chart_labels.length > 0) {
        barChart.innerHTML =
          '<canvas id="canvasChart" style="max-height: 250px; width: 100%;"></canvas>';
        const ctx = document.getElementById("canvasChart").getContext("2d");

        const gradient = ctx.createLinearGradient(0, 0, 0, 220);
        gradient.addColorStop(0, "rgba(109, 40, 217, 0.85)"); // Purple
        gradient.addColorStop(1, "rgba(59, 130, 246, 0.85)"); // Blue

        new Chart(ctx, {
          type: "bar",
          data: {
            labels: data.chart_labels,
            datasets: [
              {
                label: "Workbooks Generated",
                data: data.chart_values,
                backgroundColor: gradient,
                hoverBackgroundColor: "rgba(109, 40, 217, 0.95)",
                borderRadius: 6,
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                titleFont: { family: "Outfit", size: 12 },
                bodyFont: { family: "Inter", size: 12 },
                padding: 10,
                borderRadius: 8,
                displayColors: false,
              },
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: {
                  font: { family: "Inter", size: 11 },
                  color: "#64748b",
                },
              },
              y: {
                beginAtZero: true,
                ticks: {
                  font: { family: "Inter", size: 11 },
                  color: "#64748b",
                  stepSize: 1,
                },
                grid: { color: "rgba(15, 23, 42, 0.05)" },
              },
            },
          },
        });
      } else {
        barChart.innerHTML =
          '<p style="color:var(--color-text-muted); font-size:13px; margin:auto;">No data yet.</p>';
      }

      // 3. Render Recent Files
      if (data.recent_files && data.recent_files.length > 0) {
        recentFilesBody.innerHTML = "";
        data.recent_files.forEach((file) => {
          const dateObj = new Date(file.modified * 1000);
          const formattedDate =
            dateObj.toLocaleDateString() +
            " " +
            dateObj.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            });
          const sizeKb = (file.size / 1024).toFixed(1);

          const tr = document.createElement("tr");
          tr.innerHTML = `
                        <td>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <i class="fa-solid fa-file-excel file-icon excel" style="color: #107c41; font-size: 16px;"></i>
                                <div>
                                    <strong style="color:var(--color-text-main); font-size: 13px;">${file.module}</strong>
                                    <br>
                                    <span style="font-size: 11px; color: var(--color-text-muted); font-family: monospace;">${file.name}</span>
                                </div>
                            </div>
                        </td>
                        <td>${sizeKb} KB</td>
                        <td>${formattedDate}</td>
                        <td>
                            <div style="display:flex; align-items:center; justify-content:flex-end; gap:6px; white-space:nowrap;">
                                <button class="btn-lib-action preview" style="padding:5px 10px; font-size:11px; display:inline-flex; align-items:center; gap:4px;" onclick="openPreview('${file.name}')">
                                    <i class="fa-solid fa-eye"></i> Preview
                                </button>
                                <a href="/api/download/${file.name}" class="btn-lib-action download" style="padding:5px 10px; font-size:11px; display:inline-flex; align-items:center; gap:4px;">
                                    <i class="fa-solid fa-download"></i> Download
                                </a>
                                <button class="btn-lib-action delete" style="padding:5px 10px; font-size:11px; display:inline-flex; align-items:center; gap:4px;" onclick="deleteFile('${file.name}', this)">
                                    <i class="fa-solid fa-trash"></i> Delete
                                </button>
                            </div>
                        </td>
                    `;
          recentFilesBody.appendChild(tr);
        });
      } else {
        recentFilesBody.innerHTML = `
                    <tr>
                        <td colspan="4" class="dash-empty">
                            <i class="fa-regular fa-folder-open" style="font-size:24px; display:block; margin-bottom:8px;"></i>
                            No generated files found.
                        </td>
                    </tr>
                `;
      }

      // 5. Toggle Views
      dashLoading.classList.add("hidden");
      dashContent.classList.remove("hidden");
    } catch (error) {
      console.error("Error loading statistics:", error);
      dashLoading.innerHTML = `<i class="fa-solid fa-circle-exclamation" style="font-size:24px; color:var(--color-danger); margin-bottom:8px; display:block;"></i> Connection error: ${error.message}`;
    }
  }

  // Syntax highlighting for Python script preview
  function highlightPython(code) {
    let html = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Highlight strings (triple quotes first)
    html = html.replace(
      /("""[\s\S]*?"""|'''[\s\S]*?''')/g,
      '<span class="py-string">$1</span>',
    );

    // Single line strings
    html = html.replace(
      /((?<!\w)u?r?f?b?"[^"\\]*(?:\\.[^"\\]*)*"|(?<!\w)u?r?f?b?'[^'\\]*(?:\\.[^'\\]*)*')/g,
      (m, group) => {
        if (group.startsWith("<span")) return group;
        return `<span class="py-string">${group}</span>`;
      },
    );

    // Comments
    html = html.replace(/(#[^\n]*)/g, '<span class="py-comment">$1</span>');

    // Keywords
    const keywords = [
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield",
    ];
    const keywordRegex = new RegExp(`\\b(${keywords.join("|")})\\b`, "g");
    html = html.replace(keywordRegex, '<span class="py-keyword">$1</span>');

    // Builtins
    const builtins = [
      "print",
      "len",
      "range",
      "str",
      "int",
      "float",
      "list",
      "dict",
      "set",
      "tuple",
      "open",
      "repr",
      "enumerate",
      "min",
      "max",
      "sum",
      "any",
      "all",
      "bool",
    ];
    const builtinRegex = new RegExp(`\\b(${builtins.join("|")})\\b`, "g");
    html = html.replace(builtinRegex, '<span class="py-builtin">$1</span>');

    // Decorators
    html = html.replace(/(@\w+)/g, '<span class="py-decorator">$1</span>');

    // Functions / Classes
    html = html.replace(/\bdef\s+(\w+)/g, 'def <span class="py-def">$1</span>');
    html = html.replace(
      /\bclass\s+(\w+)/g,
      'class <span class="py-class">$1</span>',
    );

    return html;
  }

  // Convert numeric index (0, 1, 2...) to letters (A, B, C... AA, AB...)
  function getExcelColumnLabel(colIndex) {
    let label = "";
    let temp = colIndex;
    while (temp >= 0) {
      label = String.fromCharCode((temp % 26) + 65) + label;
      temp = Math.floor(temp / 26) - 1;
    }
    return label;
  }

  // Render parsed Excel workbook cells
  function renderExcelSheet(sheetData, searchQuery = "", sheetName = "") {
    excelTable.innerHTML = "";
    const rows = sheetData.rows;
    if (!rows || rows.length === 0) {
      excelTable.innerHTML =
        '<tr><td style="text-align: center; color: #64748b; padding: 20px;">Sheet is empty</td></tr>';
      return;
    }

    let maxCols = 0;
    rows.forEach((r) => {
      if (r.length > maxCols) maxCols = r.length;
    });

    const headerRow = document.createElement("tr");
    const emptyTh = document.createElement("th");
    emptyTh.className = "row-header";
    headerRow.appendChild(emptyTh);

    for (let col = 0; col < maxCols; col++) {
      const th = document.createElement("th");
      th.textContent = getExcelColumnLabel(col);
      headerRow.appendChild(th);
    }
    excelTable.appendChild(headerRow);

    rows.forEach((rowCells, rIdx) => {
      if (searchQuery && rIdx > 0) {
        const rowMatches = rowCells.some(
          (cell) =>
            cell &&
            cell.value &&
            cell.value.toLowerCase().includes(searchQuery),
        );
        if (!rowMatches) return;
      }

      const tr = document.createElement("tr");
      const rowNumberTd = document.createElement("td");
      rowNumberTd.className = "row-header";
      rowNumberTd.textContent = rIdx + 1;
      tr.appendChild(rowNumberTd);

      for (let col = 0; col < maxCols; col++) {
        const td = document.createElement("td");
        const cell = rowCells[col];

        if (cell) {
          const coord = cell.coordinate;
          let isModified = false;
          let modVal = "";
          if (excelChanges[sheetName]) {
            const match = excelChanges[sheetName].find(c => c.coordinate === coord);
            if (match) {
              isModified = true;
              modVal = match.value;
            }
          }
          td.textContent = isModified ? modVal : cell.value;

          if (cell.bg_color) {
            td.style.backgroundColor = cell.bg_color;
            const hex = cell.bg_color.replace("#", "");
            if (hex.length === 6) {
              const r = parseInt(hex.substr(0, 2), 16);
              const g = parseInt(hex.substr(2, 2), 16);
              const b = parseInt(hex.substr(4, 2), 16);
              const brightness = (r * 299 + g * 587 + b * 114) / 1000;
              if (brightness < 125) {
                td.style.color = "#ffffff";
              }
            }
          }
          if (cell.font_color) {
            td.style.color = cell.font_color;
          }
          if (cell.is_bold) {
            td.style.fontWeight = "bold";
          }

          // Make cells editable in-place!
          if (rIdx > 0) { // Do not edit headers
            td.setAttribute("contenteditable", "true");
            td.dataset.coordinate = coord;
            td.dataset.originalValue = cell.value;
            td.dataset.sheetName = sheetName;
            
            // Listen for changes
            td.addEventListener("blur", () => {
              const currentVal = td.innerText.trim();
              const originalVal = td.dataset.originalValue || "";
              if (currentVal !== originalVal) {
                if (!excelChanges[sheetName]) {
                  excelChanges[sheetName] = [];
                }
                const existing = excelChanges[sheetName].find(c => c.coordinate === coord);
                if (existing) {
                  existing.value = currentVal;
                } else {
                  excelChanges[sheetName].push({ coordinate: coord, value: currentVal });
                }
                
                if (previewSaveBtn) {
                  previewSaveBtn.classList.remove("hidden");
                }
              } else {
                if (excelChanges[sheetName]) {
                  excelChanges[sheetName] = excelChanges[sheetName].filter(c => c.coordinate !== coord);
                  if (excelChanges[sheetName].length === 0) {
                    delete excelChanges[sheetName];
                  }
                }
                if (Object.keys(excelChanges).length === 0 && previewSaveBtn) {
                  previewSaveBtn.classList.add("hidden");
                }
              }
            });
          }
        }
        tr.appendChild(td);
      }
      excelTable.appendChild(tr);
    });
  }

  // Open file preview modal
  window.openPreview = async function (filename) {
    currentFilename = filename;
    currentSheetsData = null;
    excelChanges = {};
    if (previewSaveBtn) {
      previewSaveBtn.classList.add("hidden");
    }
    previewModal.classList.remove("hidden");
    previewFilename.textContent = `Loading ${filename}...`;

    excelTabs.classList.add("hidden");
    codeViewerContainer.classList.add("hidden");
    excelViewerContainer.classList.add("hidden");
    previewCopyBtn.classList.add("hidden");
    previewSubHeader.classList.add("hidden");
    if (previewSearchInput) previewSearchInput.value = "";

    const isExcel = filename.endsWith(".xlsx");
    previewHeaderIcon.className = isExcel
      ? "fa-solid fa-file-excel file-icon excel"
      : "fa-solid fa-file-code file-icon python";

    try {
      const response = await fetch(`/api/preview/${filename}`);
      const result = await response.json();

      if (!result.success) {
        showToast("Preview error: " + result.message, "error");
        previewModal.classList.add("hidden");
        return;
      }

      previewFilename.textContent = filename;

      if (result.type === "python") {
        currentPreviewContent = result.content;
        codeViewer.innerHTML = highlightPython(result.content);
        codeViewerContainer.classList.remove("hidden");
        previewCopyBtn.classList.remove("hidden");
      } else if (result.type === "excel") {
        currentSheetsData = result.sheets;
        excelTabs.innerHTML = "";
        excelTabs.classList.remove("hidden");
        excelViewerContainer.classList.remove("hidden");
        previewSubHeader.classList.remove("hidden");

        const sheets = result.sheets;
        const sheetNames = Object.keys(sheets);

        if (sheetNames.length > 0) {
          sheetNames.forEach((sheetName, index) => {
            const tabBtn = document.createElement("button");
            tabBtn.className = "tab-btn" + (index === 0 ? " active" : "");
            tabBtn.textContent = sheetName;
            tabBtn.type = "button";
            tabBtn.addEventListener("click", () => {
              excelTabs
                .querySelectorAll(".tab-btn")
                .forEach((btn) => btn.classList.remove("active"));
              tabBtn.classList.add("active");
              if (previewSearchInput) previewSearchInput.value = "";
              renderExcelSheet(sheets[sheetName], "", sheetName);
            });
            excelTabs.appendChild(tabBtn);
          });

          renderExcelSheet(sheets[sheetNames[0]], "", sheetNames[0]);
        }
      }
    } catch (error) {
      showToast("Error loading file preview: " + error.message, "error");
      previewModal.classList.add("hidden");
    }
  };

  // Bind event listeners for search input inside Excel preview modal
  if (previewSearchInput) {
    previewSearchInput.addEventListener("input", (e) => {
      const query = e.target.value.toLowerCase().trim();
      if (currentSheetsData) {
        const activeTab = excelTabs.querySelector(".tab-btn.active");
        const activeSheetName = activeTab
          ? activeTab.textContent
          : Object.keys(currentSheetsData)[0];
        if (activeSheetName && currentSheetsData[activeSheetName]) {
          renderExcelSheet(currentSheetsData[activeSheetName], query, activeSheetName);
        }
      }
    });
  }

  // Bind click listener for save changes in preview modal
  if (previewSaveBtn) {
    previewSaveBtn.addEventListener("click", async () => {
      if (!currentFilename || Object.keys(excelChanges).length === 0) return;

      const oldHtml = previewSaveBtn.innerHTML;
      previewSaveBtn.disabled = true;
      previewSaveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

      try {
        const response = await fetch("/api/save_xlsx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: currentFilename,
            changes: excelChanges,
          }),
        });
        const result = await response.json();
        if (result.success) {
          showToast(result.message || "Changes saved successfully!", "success");
          excelChanges = {};
          previewSaveBtn.classList.add("hidden");
          // Re-load preview to display updated calculations / sheets
          await openPreview(currentFilename);
          // Reload dashboard stats
          if (typeof loadStats === "function") {
            loadStats();
          }
        } else {
          showToast(result.message || "Failed to save changes.", "error");
        }
      } catch (err) {
        showToast("Error saving: " + err.message, "error");
      } finally {
        previewSaveBtn.disabled = false;
        previewSaveBtn.innerHTML = oldHtml;
      }
    });
  }

  // Toggle export menu dropdown
  if (exportToggleBtn && exportMenu) {
    exportToggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      exportToggleBtn.classList.toggle("active");
      exportMenu.classList.toggle("hidden");
    });
  }

  // Hide export menu when clicking outside
  document.addEventListener("click", (e) => {
    if (
      exportMenu &&
      !exportMenu.classList.contains("hidden") &&
      !e.target.closest(".export-dropdown-wrapper")
    ) {
      exportMenu.classList.add("hidden");
      exportToggleBtn.classList.remove("active");
    }
  });

  // Handle export format item clicks
  document.querySelectorAll(".export-item").forEach((item) => {
    item.addEventListener("click", () => {
      const format = item.getAttribute("data-format");
      if (currentFilename && format) {
        if (exportMenu) exportMenu.classList.add("hidden");
        if (exportToggleBtn) exportToggleBtn.classList.remove("active");

        showToast(`Preparing ${format.toUpperCase()} export...`, "info", 3000);
        window.location.href = `/api/export/${currentFilename}/${format}`;
      }
    });
  });

  // Copy python script functionality
  previewCopyBtn.addEventListener("click", () => {
    navigator.clipboard
      .writeText(currentPreviewContent)
      .then(() => {
        const oldHtml = previewCopyBtn.innerHTML;
        previewCopyBtn.innerHTML =
          '<i class="fa-solid fa-check"></i> <span>Copied!</span>';
        previewCopyBtn.style.background = "rgba(16, 185, 129, 0.1)";
        previewCopyBtn.style.color = "#10b981";

        setTimeout(() => {
          previewCopyBtn.innerHTML = oldHtml;
          previewCopyBtn.style.background = "";
          previewCopyBtn.style.color = "";
        }, 2000);
      })
      .catch((err) => {
        console.error("Failed to copy text: ", err);
      });
  });

  // Close preview button
  closePreviewBtn.addEventListener("click", () => {
    previewModal.classList.add("hidden");
  });

  // Close on overlay click
  previewModal.addEventListener("click", (e) => {
    if (e.target === previewModal) {
      previewModal.classList.add("hidden");
    }
  });

  // Elegant delete modal confirmation
  window.deleteFile = function (fileName, btn) {
    const deleteModal = document.getElementById("deleteModal");
    const deleteFileNameEl = document.getElementById("deleteFileName");
    const deleteCancelBtn = document.getElementById("deleteCancelBtn");
    const deleteConfirmBtn = document.getElementById("deleteConfirmBtn");

    deleteFileNameEl.textContent = fileName;
    deleteModal.classList.remove("hidden");

    // Clean up previous listeners
    const newCancelBtn = deleteCancelBtn.cloneNode(true);
    const newConfirmBtn = deleteConfirmBtn.cloneNode(true);
    deleteCancelBtn.parentNode.replaceChild(newCancelBtn, deleteCancelBtn);
    deleteConfirmBtn.parentNode.replaceChild(newConfirmBtn, deleteConfirmBtn);

    newCancelBtn.addEventListener("click", () => {
      deleteModal.classList.add("hidden");
    });

    newConfirmBtn.addEventListener("click", () => {
      newConfirmBtn.disabled = true;
      newConfirmBtn.innerHTML = '<span class="spinner-sm"></span> Deleting...';

      fetch(`/api/delete/${fileName}`, { method: "DELETE" })
        .then((response) => response.json())
        .then((data) => {
          deleteModal.classList.add("hidden");
          if (data.success) {
            const row = btn.closest("tr");
            if (row) {
              row.style.transition = "opacity 0.3s ease, transform 0.3s ease";
              row.style.opacity = "0";
              row.style.transform = "translateX(20px)";
              setTimeout(() => {
                row.remove();
                // Reload stats in background to update total count, cards, and chart
                loadStats();
              }, 300);
            }
            showToast("File deleted successfully.", "success", 3000);
          } else {
            showToast(data.message || "Failed to delete file.", "error");
          }
        })
        .catch((err) => {
          deleteModal.classList.add("hidden");
          console.error("Delete error:", err);
          showToast("Error deleting file. Please try again.", "error");
        })
        .finally(() => {
          newConfirmBtn.disabled = false;
          newConfirmBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
        });
    });

    // Close on overlay click
    deleteModal.onclick = (e) => {
      if (e.target === deleteModal) {
        deleteModal.classList.add("hidden");
      }
    };
  };

  loadStats();
});
