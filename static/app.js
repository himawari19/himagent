document.addEventListener("DOMContentLoaded", () => {
  // ═══════════════════════════════════════════════════════
  // TOAST NOTIFICATIONS
  // ═══════════════════════════════════════════════════════
  const toastContainer = document.getElementById("toastContainer");
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

  // ═══════════════════════════════════════════════════════
  // DOM ELEMENTS
  // ═══════════════════════════════════════════════════════
  const generatorForm = document.getElementById("generatorForm");
  const pageTitleInput = document.getElementById("page_title");
  const idPrefixInput = document.getElementById("id_prefix");
  const modelNameSelect = document.getElementById("model_name");
  const apiKeyInput = document.getElementById("api_key");
  const instructionsInput = document.getElementById("instructions");
  const genDepthSelect = document.getElementById("gen_depth");

  // New Multi-Provider Elements
  const providerSelect = document.getElementById("provider_select");
  const apiKeyStatus = document.getElementById("apiKeyStatus");
  const apiKeyLabel = document.getElementById("api_key_label");

  const dropZone = document.getElementById("dropZone");
  const screenshotInput = document.getElementById("screenshot");
  const previewContainer = document.getElementById("previewContainer");
  const imagePreview = document.getElementById("imagePreview");
  const removeImgBtn = document.getElementById("removeImgBtn");
  const dropZoneContent = dropZone.querySelector(".drop-zone-content");

  const submitBtn = document.getElementById("submitBtn");
  const progressCard = document.getElementById("progressCard");
  const progressBar = document.getElementById("progressBar");
  const logOutput = document.getElementById("logOutput");
  const consoleStatus = document.getElementById("consoleStatus");

  const resultCard = document.getElementById("resultCard");
  const infoCard = document.getElementById("infoCard");

  const statCases = document.getElementById("statCases");
  const xlsxFilename = document.getElementById("xlsxFilename");
  const pyFilename = document.getElementById("pyFilename");
  const downloadBtn = document.getElementById("downloadBtn");
  const downloadPyBtn = document.getElementById("downloadPyBtn");
  const resetBtn = document.getElementById("resetBtn");

  let progressInterval = null;

  // ═══════════════════════════════════════════════════════
  // AI PROVIDERS AND MODEL CONFIGURATION
  // ═══════════════════════════════════════════════════════
  const providerModels = {
    gemini: [
      { value: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
      { value: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro Preview" },
      { value: "gemini-3-flash-preview", label: "Gemini 3 Flash Preview" },
      { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" },
      { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash-Lite" },
    ],
    openai: [
      { value: "gpt-5.5", label: "GPT-5.5" },
      { value: "gpt-5.4", label: "GPT-5.4" },
      { value: "gpt-5.4-mini", label: "GPT-5.4 mini" },
      { value: "gpt-4o", label: "GPT-4o" },
    ],
    claude: [
      { value: "claude-opus-4-8", label: "Claude Opus 4.8" },
      { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
      { value: "claude-haiku-4-5", label: "Claude Haiku 4.5" },
    ],
    mimo: [
      { value: "mimo-v2.5-pro", label: "MiMo v2.5 Pro" },
      { value: "mimo-v2.5", label: "MiMo v2.5" },
      { value: "mimo-v2-pro", label: "MiMo v2 Pro" },
      { value: "mimo-v2-flash", label: "MiMo v2 Flash" },
    ],
    deepseek: [
      { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
      { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
    ],
    grok: [
      { value: "grok-4.3", label: "Grok 4.3" },
      { value: "grok-build-0.1", label: "Grok Build 0.1" },
    ],
    mistral: [
      { value: "mistral-medium-3-5", label: "Mistral Medium 3.5" },
      { value: "mistral-small-4", label: "Mistral Small 4" },
      { value: "mistral-large-3", label: "Mistral Large 3" },
      { value: "devstral-2", label: "Devstral 2" },
    ],
  };

  const providerMeta = {
    gemini: {
      label: "Gemini API Key",
      badge: "Gemini",
      badgeClass: "gemini",
      placeholder:
        "Paste your Gemini API key — get it at aistudio.google.com/apikey",
    },
    openai: {
      label: "OpenAI API Key",
      badge: "OpenAI",
      badgeClass: "openai",
      placeholder:
        "Paste your OpenAI API key (starts with sk-...) — platform.openai.com",
    },
    claude: {
      label: "Anthropic API Key",
      badge: "Claude",
      badgeClass: "claude",
      placeholder:
        "Paste your Anthropic API key (starts with sk-ant-...) — console.anthropic.com",
    },
    mimo: {
      label: "MiMo API Key",
      badge: "MiMo",
      badgeClass: "mimo",
      placeholder: "Paste your Xiaomi MiMo API key — mimo.xiaomi.com",
    },
    deepseek: {
      label: "DeepSeek API Key",
      badge: "DeepSeek",
      badgeClass: "deepseek",
      placeholder:
        "Paste your DeepSeek API key — platform.deepseek.com/api_keys",
    },
    grok: {
      label: "xAI API Key",
      badge: "Grok",
      badgeClass: "grok",
      placeholder:
        "Paste your xAI API key (starts with xai-...) — console.x.ai",
    },
    mistral: {
      label: "Mistral API Key",
      badge: "Mistral",
      badgeClass: "mistral",
      placeholder: "Paste your Mistral API key — console.mistral.ai",
    },
  };

  function populateModels(provider) {
    if (!modelNameSelect) return;
    modelNameSelect.innerHTML = "";
    const models = providerModels[provider] || [];
    models.forEach((model) => {
      const opt = document.createElement("option");
      opt.value = model.value;
      opt.textContent = model.label;
      modelNameSelect.appendChild(opt);
    });
  }

  function setApiKeyStatus(state) {
    // state: 'checking' | 'connected' | 'failed' | ''
    if (!state) {
      apiKeyStatus.style.display = "none";
      return;
    }
    apiKeyStatus.style.display = "inline-flex";
    const cfg = {
      checking: { text: "● Checking…", color: "#94a3b8" },
      connected: { text: "● Connected", color: "#10b981" },
      failed: { text: "● Unreachable", color: "#ef4444" },
    };
    const c = cfg[state] || cfg.failed;
    apiKeyStatus.textContent = c.text;
    apiKeyStatus.style.color = c.color;
  }

  function onProviderChange() {
    const provider = providerSelect.value;
    populateModels(provider);

    const meta = providerMeta[provider];
    if (meta) {
      apiKeyLabel.textContent = meta.label;
      apiKeyInput.placeholder = meta.placeholder;
    }
    setApiKeyStatus("");
  }

  // Ping API key on blur
  apiKeyInput.addEventListener("blur", async () => {
    const key = apiKeyInput.value.trim();
    const provider = providerSelect.value;
    if (!key) {
      setApiKeyStatus("");
      return;
    }
    setApiKeyStatus("checking");
    try {
      const fd = new FormData();
      fd.append("provider", provider);
      fd.append("api_key", key);
      fd.append("model_name", modelNameSelect.value);
      const res = await fetch("/api/ping", { method: "POST", body: fd });
      const data = await res.json();
      setApiKeyStatus(data.success ? "connected" : "failed");
      if (!data.success) showToast(data.message, "warning", 8000);
    } catch {
      setApiKeyStatus("failed");
    }
  });

  providerSelect.addEventListener("change", onProviderChange);

  // Initialize on page load with default provider
  onProviderChange();

  // ═══════════════════════════════════════════════════════
  // PRESET CHIPS — toggle-based with visual active state
  // ═══════════════════════════════════════════════════════
  const activePresets = {}; // chip → data-text mapping

  document.querySelectorAll(".preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-text");
      if (!instructionsInput) return;

      if (chip.classList.contains("active")) {
        // Remove this preset
        chip.classList.remove("active");
        const lines = instructionsInput.value
          .split("\n")
          .filter((l) => l.trim());
        const remaining = lines.filter((l) => l.trim() !== text.trim());
        instructionsInput.value = remaining.join("\n");
        showToast("Preset removed.", "info", 1500);
      } else {
        // Add this preset
        chip.classList.add("active");
        if (instructionsInput.value.trim()) {
          instructionsInput.value =
            instructionsInput.value.trim() + "\n" + text;
        } else {
          instructionsInput.value = text;
        }
        showToast("Preset added!", "success", 1500);
      }
      instructionsInput.dispatchEvent(new Event("input"));
    });
  });

  // Clear Instructions button
  const clearInstructionsBtn = document.getElementById("clearInstructionsBtn");
  if (clearInstructionsBtn && instructionsInput) {
    clearInstructionsBtn.addEventListener("click", () => {
      instructionsInput.value = "";
      document
        .querySelectorAll(".preset-chip.active")
        .forEach((c) => c.classList.remove("active"));
      instructionsInput.dispatchEvent(new Event("input"));
      showToast("All instructions cleared.", "info", 1500);
    });
  }

  // ═══════════════════════════════════════════════════════
  // DRAG & DROP / FILE SELECTION HANDLERS
  // ═══════════════════════════════════════════════════════
  let selectedFiles = [];

  // Click on dropzone triggers input click
  dropZone.addEventListener("click", (e) => {
    // Prevent click if clicking inside preview container or delete buttons
    if (e.target.closest("#previewContainer")) return;
    screenshotInput.click();
  });

  // File input change
  screenshotInput.addEventListener("change", () => {
    addFiles(screenshotInput.files);
  });

  // Drag events
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(
      eventName,
      (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add("drag-active");
      },
      false,
    );
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(
      eventName,
      (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove("drag-active");
      },
      false,
    );
  });

  // Drop file
  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      addFiles(files);
    }
  });

  // ═══════════════════════════════════════════════════════
  // CLIPBOARD PASTE HANDLER (Ctrl+V / Cmd+V)
  // ═══════════════════════════════════════════════════════
  document.addEventListener("paste", (e) => {
    // Only intercept paste if user is NOT typing in a text input/textarea
    const activeTag = document.activeElement?.tagName?.toLowerCase();
    if (activeTag === "input" || activeTag === "textarea") {
      // Allow normal paste in form fields unless it's an image paste
      const clipboardData = e.clipboardData || window.clipboardData;
      if (!clipboardData) return;
      const hasImage = Array.from(clipboardData.items).some((item) =>
        item.type.startsWith("image/"),
      );
      if (!hasImage) return; // Let text paste go through normally
    }

    const clipboardData = e.clipboardData || window.clipboardData;
    if (!clipboardData) return;

    const items = clipboardData.items;
    const pastedFiles = [];

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        const blob = items[i].getAsFile();
        if (blob) {
          // Create a proper File object with a descriptive name
          const timestamp = Date.now();
          const ext =
            blob.type.split("/")[1] === "jpeg"
              ? "jpg"
              : blob.type.split("/")[1] || "png";
          const fileName = `pasted_screen_${timestamp}_${i + 1}.${ext}`;
          const file = new File([blob], fileName, { type: blob.type });
          pastedFiles.push(file);
        }
      }
    }

    if (pastedFiles.length > 0) {
      e.preventDefault();
      addFiles(pastedFiles);

      // Visual feedback: pulse animation on the drop zone
      dropZone.classList.add("paste-flash");
      setTimeout(() => dropZone.classList.remove("paste-flash"), 700);
    }
  });

  // Add files to selection array
  function addFiles(filesList) {
    const remainingSlots = 10 - selectedFiles.length;
    if (remainingSlots <= 0) {
      showToast("Maximum 10 screenshots reached.", "warning");
      return;
    }

    const filesArray = Array.from(filesList);
    const validImages = filesArray.filter((file) =>
      file.type.startsWith("image/"),
    );

    if (validImages.length === 0) {
      showToast("Please select valid image files (JPG, PNG, WEBP).", "warning");
      return;
    }

    // Add up to remaining slots limit
    const filesToAdd = validImages.slice(0, remainingSlots);
    selectedFiles = [...selectedFiles, ...filesToAdd];

    if (validImages.length > remainingSlots) {
      showToast(
        `Only added first ${remainingSlots} images. Maximum limit is 10.`,
        "warning",
      );
    }

    renderPreviews();
  }

  // ═══════════════════════════════════════════════════════
  // LOGGING UTILITIES
  // ═══════════════════════════════════════════════════════
  const loaderModal = document.getElementById("loaderModal");
  const loaderLogOutput = document.getElementById("loaderLogOutput");
  const loaderBadge = document.getElementById("loaderBadge");
  const loaderTitle = document.getElementById("loaderTitle");
  const loaderSubtitle = document.getElementById("loaderSubtitle");
  const spinnerContainer = loaderModal.querySelector(".spinner-container");
  const magicIcon = loaderModal.querySelector(".magic-icon-spinner");

  // Stepper DOM Elements
  const step1 = document.getElementById("step1");
  const step2 = document.getElementById("step2");
  const step3 = document.getElementById("step3");
  const step4 = document.getElementById("step4");
  const step2Label = step2.querySelector(".step-label");

  // Fun rotating subtitle messages
  const funMessages = [
    "🧪 Brewing a potion of test scenarios...",
    "🔬 Examining every pixel like a detective...",
    "🎯 Preparing dynamic QA scenarios for your test plan...",
    "📋 Counting buttons... there are a LOT of buttons...",
    "🧠 AI is thinking really hard right now...",
    "☕ The AI grabbed a coffee, give it a sec...",
    "🎨 Painting each cell in your spreadsheet with love...",
    "🐛 Hunting bugs before they even exist...",
    "🚀 Almost there! The test cases are taking off...",
    "📊 Building the most beautiful Excel you've ever seen...",
    "🤖 Teaching robots to break your UI (in a good way)...",
    "🧩 Solving the puzzle of your test coverage...",
    "🏗️ Constructing your QA fortress, brick by brick...",
    "🎪 Juggling Positive, Negative, and Boundary cases...",
    "🔍 Inspecting UI elements with a magnifying glass...",
    "📝 Writing test steps so good, QA will cry happy tears...",
    "🌈 Sprinkling WCAG accessibility magic everywhere...",
    "⚡ Stress-testing your patience (and your app)...",
    "🛡️ Crafting XSS attacks for your own protection...",
    "📱 Making sure it works on phones, tablets, even a fridge...",
    "🎭 Role-playing as 6 different browsers simultaneously...",
    "🔧 Fine-tuning edge cases that nobody thinks about...",
    "🎵 Humming a tune while generating your workbook...",
    "🧲 Attracting all the corner cases from the shadows...",
    "🏎️ Racing through cross-browser compatibility checks...",
  ];
  let subtitleInterval = null;

  function startSubtitleRotation() {
    let msgIndex = 0;
    loaderTitle.style.transition = "opacity 0.4s ease";
    loaderTitle.textContent = funMessages[0];

    subtitleInterval = setInterval(() => {
      loaderTitle.style.opacity = "0";
      setTimeout(() => {
        msgIndex = (msgIndex + 1) % funMessages.length;
        loaderTitle.textContent = funMessages[msgIndex];
        loaderTitle.style.opacity = "1";
      }, 400);
    }, 3500);
  }

  function stopSubtitleRotation() {
    if (subtitleInterval) {
      clearInterval(subtitleInterval);
      subtitleInterval = null;
    }
  }

  function clearLogs() {
    loaderLogOutput.innerHTML = "";
    logOutput.innerHTML = "";
  }

  function addLog(message, type = "info") {
    const line = document.createElement("div");
    line.className = `log-line ${type}`;

    const timestamp = new Date().toLocaleTimeString();
    line.innerHTML = `<span style="color: #64748b">[${timestamp}]</span> ${message}`;

    // Output to both console elements
    const lineClone = line.cloneNode(true);
    loaderLogOutput.appendChild(line);
    logOutput.appendChild(lineClone);

    loaderLogOutput.scrollTop = loaderLogOutput.scrollHeight;
    logOutput.scrollTop = logOutput.scrollHeight;
  }

  // ═══════════════════════════════════════════════════════
  // STEPPER MANAGEMENT HELPERS
  // ═══════════════════════════════════════════════════════
  function setStepState(stepElement, state) {
    if (!stepElement) return;
    stepElement.className = `step-item ${state}`;
    const iconContainer = stepElement.querySelector(".step-icon");

    if (state === "active") {
      iconContainer.innerHTML =
        '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    } else if (state === "completed") {
      iconContainer.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
    } else if (state === "failed") {
      iconContainer.innerHTML = '<i class="fa-solid fa-circle-xmark"></i>';
    } else {
      iconContainer.innerHTML = '<i class="fa-solid fa-circle"></i>';
    }
  }

  // ═══════════════════════════════════════════════════════
  // GENERATION PROGRESS MANAGER
  // ═══════════════════════════════════════════════════════
  function startProgress() {
    clearLogs();

    const providerName =
      providerMeta[providerSelect.value]?.badge || providerSelect.value;

    // Show non-closable loader modal & update text
    loaderModal.classList.remove("hidden");
    loaderModal.style.setProperty("--loader-progress", "0%");
    loaderBadge.textContent = "PROCESSING";
    loaderBadge.style.background = "rgba(109, 40, 217, 0.2)";
    loaderBadge.style.color = "#a78bfa";

    // Update step 2 label dynamically to match selected provider
    step2Label.textContent = `${providerName} Vision Analysis`;

    // Reset steppers — flow matches actual backend:
    // 1. Validate & Upload → 2. AI Vision Analysis → 3. Parse & Synthesize → 4. Write Files
    setStepState(step1, "active");
    setStepState(step2, "pending");
    setStepState(step3, "pending");
    setStepState(step4, "pending");

    // Start fun subtitle rotation
    startSubtitleRotation();

    progressCard.classList.add("hidden");
    infoCard.classList.add("hidden");
    resultCard.classList.add("hidden");
    generatorForm.classList.add("hidden");
    submitBtn.disabled = true;

    consoleStatus.textContent = "RUNNING";
    consoleStatus.style.background = "rgba(139, 92, 246, 0.2)";
    consoleStatus.style.color = "#a78bfa";

    // Step 1 logs: Validating & Uploading
    addLog("Initializing generation pipeline...", "info");
    addLog(
      `Validating ${selectedFiles.length} SUT screenshot(s)... checking format & dimensions`,
      "info",
    );

    let progressVal = 0;
    progressBar.style.width = "0%";

    // Smooth simulated progress — designed to NEVER look stuck
    // The progress asymptotically approaches 75% during the AI wait.
    // Steps 3 & 4 only trigger when the actual server response arrives.
    let tickCount = 0;
    progressInterval = setInterval(() => {
      tickCount++;

      if (progressVal < 10) {
        // Step 1: Validate & Upload (fast, ~3 seconds)
        progressVal += Math.floor(Math.random() * 3) + 3;
      } else if (progressVal < 75) {
        // Step 2: AI Vision Analysis (asymptotic crawl — never caps out)
        // Increment gets smaller as we approach 75%, ensuring it ALWAYS moves
        const remaining = 75 - progressVal;
        const increment = Math.max(
          0.15,
          remaining * 0.02 + Math.random() * 0.3,
        );
        progressVal = Math.min(74.9, progressVal + increment);
      }
      // Above 75%: only stopProgress() advances further

      progressBar.style.width = `${Math.floor(progressVal)}%`;
      loaderModal.style.setProperty(
        "--loader-progress",
        `${Math.floor(progressVal)}%`,
      );

      // ── Step transitions & log entries (matching actual backend flow) ──

      // Step 1 → 2: Done validating, now connecting to AI
      if (progressVal >= 10 && !logsTriggered.step1Done) {
        addLog(
          "Screenshots encrypted & uploaded to memory buffer ✓",
          "success",
        );
        setStepState(step1, "completed");
        setStepState(step2, "active");
        addLog(`Connecting to ${providerName} API Gateway...`, "info");
        addLog(
          `Transmitting ${selectedFiles.length} screenshot(s) + system prompt to ${providerName}...`,
          "info",
        );
        logsTriggered.step1Done = true;
      }
      // Mid Step 2: AI is processing (the long wait — spread messages out)
      if (progressVal >= 20 && !logsTriggered.step2Mid1) {
        addLog(
          `${providerName} model performing OCR and layout analysis...`,
          "info",
        );
        logsTriggered.step2Mid1 = true;
      }
      if (progressVal >= 35 && !logsTriggered.step2Mid2) {
        addLog(
          "Mapping interactive elements, form controls & navigation flow...",
          "info",
        );
        logsTriggered.step2Mid2 = true;
      }
      if (progressVal >= 48 && !logsTriggered.step2Mid3) {
        addLog(
          "AI generating exhaustive test scenarios... (this takes a moment)",
          "info",
        );
        logsTriggered.step2Mid3 = true;
      }
      if (progressVal >= 58 && !logsTriggered.step2Mid4) {
        addLog(
          "Synthesizing Positive, Negative & Boundary case coverage...",
          "info",
        );
        logsTriggered.step2Mid4 = true;
      }
      if (progressVal >= 66 && !logsTriggered.step2Mid5) {
        addLog(
          "Compiling WCAG 2.1 AA audits & cross-browser checks...",
          "info",
        );
        logsTriggered.step2Mid5 = true;
      }

      // ── Heartbeat messages: show activity even when progress crawls ──
      // Triggers every ~15 ticks (~9 seconds) once past 50%
      if (progressVal >= 50 && progressVal < 75 && tickCount % 15 === 0) {
        const heartbeats = [
          `Still waiting for ${providerName} response... hang tight! ⏳`,
          "AI is crunching through all those edge cases... 🧠",
          "Generating security & accessibility test scenarios... 🛡️",
          "This usually takes 30-90 seconds depending on complexity... ⏱️",
          `${providerName} is building your 50+ test cases... almost there! 🔄`,
          "Cross-checking mobile responsive & performance scenarios... 📱",
          "The more elements detected, the longer it takes (but the better the result!) 💪",
          "Patience is a QA virtue... your test plan will be worth it! ✨",
        ];
        const heartbeatIdx = Math.floor(tickCount / 15) % heartbeats.length;
        addLog(heartbeats[heartbeatIdx], "info");
      }
    }, 600);
  }

  let logsTriggered = {
    step1Done: false,
    step2Mid1: false,
    step2Mid2: false,
    step2Mid3: false,
    step2Mid4: false,
    step2Mid5: false,
  };

  function stopProgress(success, messageOrCallback = "", onDone = null) {
    // Support stopProgress(true, callback) shorthand
    if (typeof messageOrCallback === "function") {
      onDone = messageOrCallback;
      messageOrCallback = "";
    }
    const message = messageOrCallback;
    clearInterval(progressInterval);
    stopSubtitleRotation();
    submitBtn.disabled = false;

    if (success) {
      progressBar.style.width = "100%";
      loaderModal.style.setProperty("--loader-progress", "100%");
      consoleStatus.textContent = "COMPLETED";
      consoleStatus.style.background = "rgba(16, 185, 129, 0.2)";
      consoleStatus.style.color = "#10b981";

      loaderBadge.textContent = "SUCCESS";
      loaderBadge.style.background = "rgba(16, 185, 129, 0.2)";
      loaderBadge.style.color = "#10b981";

      // Update title to success message
      loaderTitle.style.opacity = "0";
      setTimeout(() => {
        loaderTitle.textContent =
          "🎉 Your test plan is ready! Check it out below.";
        loaderTitle.style.opacity = "1";
      }, 300);

      // Animate remaining steps 2→3→4 with realistic log messages
      // Step 2: AI response received
      addLog(
        `${providerMeta[providerSelect.value]?.badge || "AI"} response received ✓`,
        "success",
      );
      setStepState(step1, "completed");
      setStepState(step2, "completed");
      setStepState(step3, "active");
      progressBar.style.width = "80%";
      loaderModal.style.setProperty("--loader-progress", "80%");

      // Step 3: Parse & Synthesize (quick animation)
      setTimeout(() => {
        addLog("Decoding structured JSON response...", "info");
        addLog("Normalizing test case fields & validating schema...", "info");
        progressBar.style.width = "88%";
        loaderModal.style.setProperty("--loader-progress", "88%");

        setTimeout(() => {
          addLog(
            "Structuring and grouping test scenarios...",
            "info",
          );
          addLog("Test case synthesis complete ✓", "success");
          setStepState(step3, "completed");
          setStepState(step4, "active");
          progressBar.style.width = "94%";
          loaderModal.style.setProperty("--loader-progress", "94%");

          // Step 4: Writing files
          setTimeout(() => {
            addLog("Assembling Excel workbook with openpyxl...", "info");
            addLog(
              "Writing TEST PLAN and SUMMARY sheets...",
              "info",
            );
            progressBar.style.width = "97%";
            loaderModal.style.setProperty("--loader-progress", "97%");

            setTimeout(() => {
              addLog(
                "Saving .xlsx and .py files to outputs/ folder...",
                "success",
              );
              progressBar.style.width = "100%";
              loaderModal.style.setProperty("--loader-progress", "100%");
              setStepState(step4, "completed");
              addLog(
                "✅ Generation complete! All files ready in outputs/ folder.",
                "success",
              );

              // Spinner → checkmark
              spinnerContainer.classList.add("done");
              magicIcon.classList.remove("fa-wand-magic-sparkles");
              magicIcon.classList.add("fa-circle-check");

              // Show manual close button
              const closeBtn = document.createElement("button");
              closeBtn.className = "btn-done";
              closeBtn.innerHTML =
                '<i class="fa-solid fa-rocket"></i> Your plan is ready — Let\'s go!';
              closeBtn.type = "button";
              closeBtn.addEventListener("click", () => {
                loaderModal.classList.add("hidden");
                if (onDone) onDone();
              });
              loaderModal
                .querySelector(".loader-content")
                .appendChild(closeBtn);
            }, 500);
          }, 400);
        }, 400);
      }, 300);
    } else {
      loaderModal.style.setProperty(
        "--loader-progress",
        progressBar.style.width || "0%",
      );
      consoleStatus.textContent = "FAILED";
      consoleStatus.style.background = "rgba(239, 68, 68, 0.2)";
      consoleStatus.style.color = "#ef4444";

      loaderBadge.textContent = "FAILED";
      loaderBadge.style.background = "rgba(239, 68, 68, 0.2)";
      loaderBadge.style.color = "#ef4444";

      // Update title to error
      loaderTitle.style.opacity = "0";
      setTimeout(() => {
        loaderTitle.textContent =
          "😞 Something went wrong. Check the error below.";
        loaderTitle.style.opacity = "1";
      }, 300);

      // Mark current active step as failed
      if (step4.classList.contains("active")) setStepState(step4, "failed");
      else if (step3.classList.contains("active"))
        setStepState(step3, "failed");
      else if (step2.classList.contains("active"))
        setStepState(step2, "failed");
      else setStepState(step1, "failed");

      addLog(`Error: ${message}`, "error");
      showToast(message, "error", 10000);

      // Spinner → error X
      spinnerContainer.classList.add("done");
      magicIcon.classList.remove("fa-wand-magic-sparkles");
      magicIcon.classList.add("fa-circle-xmark");
      magicIcon.style.setProperty("-webkit-text-fill-color", "#ef4444");
      magicIcon.style.color = "#ef4444";
      loaderModal.querySelector(".glow-spinner").style.border =
        "4px solid #ef4444";
      loaderModal.querySelector(".glow-spinner").style.boxShadow =
        "0 0 20px rgba(239,68,68,0.35)";

      // If failed, allow user to close the loader overlay
      const dismissBtn = document.createElement("button");
      dismissBtn.className = "btn-secondary";
      dismissBtn.style.cssText =
        "margin-top:20px;width:100%;justify-content:center;background:rgba(239,68,68,0.08);color:#dc2626;border-color:rgba(239,68,68,0.3)";
      dismissBtn.innerHTML =
        '<i class="fa-solid fa-xmark"></i> Dismiss & Try Again';
      dismissBtn.type = "button";
      dismissBtn.addEventListener("click", () => {
        loaderModal.classList.add("hidden");
        generatorForm.classList.remove("hidden");
      });
      loaderModal.querySelector(".loader-content").appendChild(dismissBtn);
    }
  }

  // ═══════════════════════════════════════════════════════
  // LIBRARY ACTIONS & PREVIEW SYSTEM
  // ═══════════════════════════════════════════════════════
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

  // Load library items from server
  async function loadLibrary() {
    try {
      const response = await fetch("/api/files");
      const result = await response.json();

      const libraryList = document.getElementById("libraryList");
      libraryList.innerHTML = "";

      if (result.success && result.files && result.files.length > 0) {
        result.files.forEach((file) => {
          const item = document.createElement("div");
          item.className = "library-item";

          const isExcel = file.type === "excel";
          const iconClass = isExcel
            ? "fa-file-excel excel"
            : "fa-file-code python";
          const formattedSize = (file.size / 1024).toFixed(1) + " KB";

          // Format timestamp
          const dateObj = new Date(file.modified * 1000);
          const formattedDate =
            dateObj.toLocaleDateString() +
            " " +
            dateObj.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            });

          item.innerHTML = `
                        <div class="lib-file-details">
                            <i class="fa-solid ${iconClass} file-icon"></i>
                            <div class="lib-file-meta">
                                <span class="lib-file-name">${file.name}</span>
                                <span class="lib-file-sub">
                                    <span><i class="fa-solid fa-weight-hanging"></i> ${formattedSize}</span>
                                    <span><i class="fa-solid fa-clock"></i> ${formattedDate}</span>
                                </span>
                            </div>
                        </div>
                        <div class="lib-actions">
                            <button class="btn-lib-action preview" type="button">
                                <i class="fa-solid fa-eye"></i> Preview
                            </button>
                            <a href="/api/download/${file.name}" class="btn-lib-action download">
                                <i class="fa-solid fa-download"></i> Download
                            </a>
                            <button class="btn-lib-action delete" type="button">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    `;

          // Bind event for preview
          item.querySelector(".preview").addEventListener("click", () => {
            openPreview(file.name);
          });

          // Bind delete button event
          item.querySelector(".delete").addEventListener("click", (e) => {
            e.stopPropagation();
            deleteFile(file.name, e.currentTarget);
          });

          libraryList.appendChild(item);
        });
      } else {
        libraryList.innerHTML = `
                    <div class="library-empty">
                        <i class="fa-regular fa-folder-open empty-icon"></i>
                        <p>No generated files found in <code>outputs/</code> directory.</p>
                    </div>
                `;
      }
    } catch (error) {
      console.error("Error loading library:", error);
    }
  }

  function deleteFile(fileName, btn) {
    const deleteModal = document.getElementById("deleteModal");
    const deleteFileNameEl = document.getElementById("deleteFileName");
    const deleteCancelBtn = document.getElementById("deleteCancelBtn");
    const deleteConfirmBtn = document.getElementById("deleteConfirmBtn");

    // Show modal with filename
    deleteFileNameEl.textContent = fileName;
    deleteModal.classList.remove("hidden");

    // Clean up previous listeners
    const newCancelBtn = deleteCancelBtn.cloneNode(true);
    const newConfirmBtn = deleteConfirmBtn.cloneNode(true);
    deleteCancelBtn.parentNode.replaceChild(newCancelBtn, deleteCancelBtn);
    deleteConfirmBtn.parentNode.replaceChild(newConfirmBtn, deleteConfirmBtn);

    // Cancel — close modal
    newCancelBtn.addEventListener("click", () => {
      deleteModal.classList.add("hidden");
    });

    // Confirm — proceed with deletion
    newConfirmBtn.addEventListener("click", () => {
      newConfirmBtn.disabled = true;
      newConfirmBtn.innerHTML = '<span class="spinner-sm"></span> Deleting...';

      fetch(`/api/delete/${fileName}`, { method: "DELETE" })
        .then((response) => response.json())
        .then((data) => {
          deleteModal.classList.add("hidden");
          if (data.success) {
            const row = btn.closest(".library-item");
            if (row) {
              row.style.transition = "opacity 0.3s ease, transform 0.3s ease";
              row.style.opacity = "0";
              row.style.transform = "translateX(20px)";
              setTimeout(() => row.remove(), 300);
            }
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

    // Generate Header column tags (A, B, C...)
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

    // Render rows
    rows.forEach((rowCells, rIdx) => {
      // Apply search filter if query is present, except for the header row
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

      // Row number header
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

          // Background styling
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
  async function openPreview(filename) {
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

          // Render first sheet by default
          renderExcelSheet(sheets[sheetNames[0]], "", sheetNames[0]);
        }
      }
    } catch (error) {
      showToast("Error loading file preview: " + error.message, "error");
      previewModal.classList.add("hidden");
    }
  }

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

  // Refresh library button
  document
    .getElementById("refreshLibraryBtn")
    .addEventListener("click", loadLibrary);

  // Initial load of library on start
  loadLibrary();

  // ═══════════════════════════════════════════════════════
  // FORM SUBMISSION (API CALL)
  // ═══════════════════════════════════════════════════════
  generatorForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    console.log("[DEBUG] Form submitted");

    if (selectedFiles.length === 0) {
      console.log("[DEBUG] No files selected — aborting");
      showToast("Please upload at least one screenshot.", "warning");
      return;
    }
    console.log(
      "[DEBUG] Files:",
      selectedFiles.map((f) => f.name + " (" + f.size + "b)"),
    );

    // Clean any residual dismiss buttons in loader modal
    const oldDismiss = loaderModal.querySelector(
      ".loader-content .btn-secondary, .loader-content .btn-done",
    );
    if (oldDismiss) oldDismiss.remove();

    // Reset spinner to loading state
    spinnerContainer.classList.remove("done");
    magicIcon.classList.remove("fa-circle-check", "fa-circle-xmark");
    magicIcon.classList.add("fa-wand-magic-sparkles");
    magicIcon.style.removeProperty("-webkit-text-fill-color");
    magicIcon.style.removeProperty("color");
    const glowSpinner = loaderModal.querySelector(".glow-spinner");
    glowSpinner.style.removeProperty("border");
    glowSpinner.style.removeProperty("box-shadow");

    // Reset tracking logs
    logsTriggered = {
      step1Done: false,
      step2Mid1: false,
      step2Mid2: false,
      step2Mid3: false,
      step2Mid4: false,
      step2Mid5: false,
    };
    startProgress();
    console.log("[DEBUG] startProgress() called");

    // Compile payload
    const formData = new FormData();
    selectedFiles.forEach((file) => {
      formData.append("screenshot", file);
    });
    formData.append("page_title", pageTitleInput.value);
    formData.append("id_prefix", idPrefixInput.value);
    formData.append("model_name", modelNameSelect.value);
    formData.append("api_key", apiKeyInput.value);
    formData.append("provider", providerSelect.value);
    formData.append("instructions", instructionsInput.value);
    if (genDepthSelect) {
      formData.append("gen_depth", genDepthSelect.value);
    }
    console.log(
      "[DEBUG] Payload ready — page_title:",
      pageTitleInput.value,
      "| provider:",
      providerSelect.value,
      "| model:",
      modelNameSelect.value,
      "| gen_depth:",
      genDepthSelect ? genDepthSelect.value : "fast"
    );

    try {
      console.log("[DEBUG] Sending POST /api/generate...");
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        console.error("[DEBUG] Request timed out after 5 minutes");
        controller.abort();
      }, 300000);

      const response = await fetch("/api/generate", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      console.log("[DEBUG] Response status:", response.status);

      const result = await response.json();
      console.log("[DEBUG] Result:", result.success, result.message || "");

      if (result.success) {
        // Populate results immediately (hidden)
        statCases.textContent = result.test_case_count;
        xlsxFilename.textContent = result.xlsx_file;
        pyFilename.textContent = result.py_file;
        downloadBtn.href = result.download_url;
        downloadPyBtn.href = `/api/download/${result.py_file}`;
        loadLibrary();

        stopProgress(true, () => {
          // Called when user clicks Done — show result card
          resultCard.classList.remove("hidden");
        });
      } else {
        stopProgress(false, result.message);
      }
    } catch (error) {
      console.error("[DEBUG] Fetch error:", error);
      let errorMsg = error.message || "An unexpected connection error occurred.";
      if (error.name === "AbortError") {
        errorMsg = "Request timed out after 5 minutes. The AI model may be taking too long to respond. Please try again with fewer screenshots or a faster model.";
      } else if (errorMsg === "Failed to fetch") {
        errorMsg = "Failed to connect to the server. The Flask server may have crashed or restarted during processing. Please check that the server is running (python app.py) and try again.";
      }
      stopProgress(false, errorMsg);
    }
  });

  // ═══════════════════════════════════════════════════════
  // RESET PANEL
  // ═══════════════════════════════════════════════════════
  resetBtn.addEventListener("click", () => {
    // Clear fields
    pageTitleInput.value = "";
    idPrefixInput.value = "";
    apiKeyInput.value = "";
    providerSelect.value = "gemini";
    onProviderChange();
    instructionsInput.value = "";
    if (genDepthSelect) genDepthSelect.value = "fast";

    selectedFiles = [];
    renderPreviews();

    // Hide detect btn and suggestion bar on reset
    detectBtn.classList.add("hidden");
    suggestionBar.classList.add("hidden");
    suggestionBar.innerHTML = "";

    // Toggle card visibility back
    resultCard.classList.add("hidden");
    infoCard.classList.remove("hidden");
    generatorForm.classList.remove("hidden");

    progressBar.style.width = "0%";
  });

  // ═══════════════════════════════════════════════════════
  // AUTO-DETECT MODULE TYPE + AI NAMING SUGGESTION
  // ═══════════════════════════════════════════════════════
  const detectBtn = document.getElementById("detectBtn");
  const detectBtnText = document.getElementById("detectBtnText");
  const suggestionBar = document.getElementById("suggestionBar");

  // Show detect button when files are selected
  function renderPreviews() {
    const previewGrid = document.getElementById("previewGrid");
    previewGrid.innerHTML = "";

    if (selectedFiles.length === 0) {
      previewContainer.classList.add("hidden");
      dropZoneContent.classList.remove("hidden");
      screenshotInput.value = "";
      detectBtn.classList.add("hidden");
      suggestionBar.classList.add("hidden");
      suggestionBar.innerHTML = "";
      return;
    }

    dropZoneContent.classList.add("hidden");
    previewContainer.classList.remove("hidden");
    detectBtn.classList.remove("hidden");

    selectedFiles.forEach((file, index) => {
      const reader = new FileReader();
      const itemDiv = document.createElement("div");
      itemDiv.className = "preview-item";
      const img = document.createElement("img");
      const labelSpan = document.createElement("span");
      labelSpan.className = "preview-item-label";
      labelSpan.textContent = `Screen ${index + 1}`;
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "preview-item-delete";
      deleteBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      deleteBtn.title = "Remove screen";
      deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectedFiles.splice(index, 1);
        renderPreviews();
      });
      reader.onload = (e) => {
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
      itemDiv.appendChild(img);
      itemDiv.appendChild(labelSpan);
      itemDiv.appendChild(deleteBtn);
      previewGrid.appendChild(itemDiv);
    });
  }

  removeImgBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selectedFiles = [];
    renderPreviews();
  });

  // Detect module via API
  detectBtn.addEventListener("click", async () => {
    if (selectedFiles.length === 0) return;

    const apiKey = apiKeyInput.value.trim();
    const modelName = modelNameSelect.value;

    if (!apiKey && !window._envApiKeyAvailable) {
      // soft warning — still attempt, server will reject if no env key
    }

    detectBtn.disabled = true;
    detectBtnText.innerHTML = '<span class="spinner-sm"></span> Detecting...';
    detectBtnText.previousElementSibling?.remove(); // remove icon temp
    suggestionBar.classList.add("hidden");
    suggestionBar.innerHTML = "";

    const formData = new FormData();
    formData.append("screenshot", selectedFiles[0]);
    formData.append("api_key", apiKey);
    formData.append("model_name", modelName);
    formData.append("provider", providerSelect.value);

    try {
      const res = await fetch("/api/detect", {
        method: "POST",
        body: formData,
      });
      const result = await res.json();

      if (result.success) {
        renderSuggestionBar(result);
      } else {
        suggestionBar.innerHTML = `<span class="suggestion-label" style="color:#ef4444"><i class="fa-solid fa-circle-exclamation"></i> Detection failed: ${result.message}</span>`;
        suggestionBar.classList.remove("hidden");
      }
    } catch (err) {
      suggestionBar.innerHTML = `<span class="suggestion-label" style="color:#ef4444"><i class="fa-solid fa-circle-exclamation"></i> ${err.message}</span>`;
      suggestionBar.classList.remove("hidden");
    } finally {
      detectBtn.disabled = false;
      detectBtnText.innerHTML = "Auto-Detect Module Type";
      // Re-insert icon
      const icon = document.createElement("i");
      icon.className = "fa-solid fa-wand-magic-sparkles";
      detectBtn.insertBefore(icon, detectBtnText);
    }
  });

  function renderSuggestionBar(result) {
    suggestionBar.innerHTML = "";

    // Label
    const label = document.createElement("span");
    label.className = "suggestion-label";
    label.innerHTML = '<i class="fa-solid fa-lightbulb"></i> AI Suggestion:';
    suggestionBar.appendChild(label);

    // Module name chip (click to fill page_title)
    const nameChip = document.createElement("button");
    nameChip.type = "button";
    nameChip.className = "suggestion-chip";
    nameChip.title = "Click to use as Page/Module Title";
    nameChip.innerHTML = `<i class="fa-solid fa-file-signature"></i> ${result.module_name}`;
    nameChip.addEventListener("click", () => {
      pageTitleInput.value = result.module_name;
      nameChip.style.background = "rgba(5,150,105,0.12)";
      nameChip.style.borderColor = "rgba(5,150,105,0.4)";
      nameChip.style.color = "#059669";
    });
    suggestionBar.appendChild(nameChip);

    // TC prefix chip (click to fill id_prefix)
    const prefixChip = document.createElement("button");
    prefixChip.type = "button";
    prefixChip.className = "suggestion-chip";
    prefixChip.title = "Click to use as TC-ID Prefix";
    prefixChip.innerHTML = `<i class="fa-solid fa-hashtag"></i> ${result.tc_prefix}`;
    prefixChip.addEventListener("click", () => {
      idPrefixInput.value = result.tc_prefix;
      prefixChip.style.background = "rgba(5,150,105,0.12)";
      prefixChip.style.borderColor = "rgba(5,150,105,0.4)";
      prefixChip.style.color = "#059669";
    });
    suggestionBar.appendChild(prefixChip);

    // Module type badge (display only)
    const typeBadge = document.createElement("span");
    typeBadge.className = "suggestion-chip type-badge";
    typeBadge.innerHTML = `<i class="fa-solid fa-tag"></i> ${result.module_type}`;
    suggestionBar.appendChild(typeBadge);

    // Confidence tag
    if (result.confidence !== undefined) {
      const confTag = document.createElement("span");
      confTag.className = "confidence-tag";
      confTag.textContent = `${result.confidence}% confident`;
      suggestionBar.appendChild(confTag);
    }

    // Description
    if (result.description) {
      const desc = document.createElement("span");
      desc.className = "suggestion-desc";
      desc.textContent = result.description;
      suggestionBar.appendChild(desc);
    }

    suggestionBar.classList.remove("hidden");
  }

  // ═══════════════════════════════════════════════════════
  // INLINE EXCEL EDITING SAVE ACTION
  // ═══════════════════════════════════════════════════════
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
          // Reload library on index page to show updated date/size
          if (typeof loadLibrary === "function") {
            loadLibrary();
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
});
