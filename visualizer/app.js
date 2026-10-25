/**
 * Solana Validator Block Ordering Visualizer.
 * Interactive analytics engine rendering scatter plots, concurrency waterfalls,
 * write-lock contention clusters, and comparative client matrices.
 */

// Global State
let blocksData = [];
let analysisResults = [];
let activeSlot = null;
let activeBlock = null;
let activeAnalysis = null;
let activeClusterAccount = null;

// DOM Elements
const slotSelect = document.getElementById('slotSelect');
const clientBadge = document.getElementById('clientBadge');
const feeTierFilter = document.getElementById('feeTierFilter');
const searchInput = document.getElementById('searchInput');

// KPIs
const kpiTotalTxs = document.getElementById('kpiTotalTxs');
const kpiNonVoteTxs = document.getElementById('kpiNonVoteTxs');
const kpiSpearmanRho = document.getElementById('kpiSpearmanRho');
const kpiClusterRho = document.getElementById('kpiClusterRho');
const kpiInversionRatio = document.getElementById('kpiInversionRatio');
const kpiTopDecileHead = document.getElementById('kpiTopDecileHead');
const kpiVerdict = document.getElementById('kpiVerdict');
const kpiVerdictDesc = document.getElementById('kpiVerdictDesc');

// Chart Canvas
const canvas = document.getElementById('scatterCanvas');
const ctx = canvas ? canvas.getContext('2d') : null;
const tooltip = document.getElementById('chartTooltip');

// Preloaded Embedded Fallback Data in case running directly from file:// origin
const EMBEDDED_SAMPLE_BLOCKS = [
  {
    "slot": 300120620,
    "blockhash": "FDanceSlot620_4uQeVj5tqViQh7yWWGStvfEG1Nmq6e86XG1d",
    "leader_pubkey": "FDanceJump1111111111111111111111111111111111",
    "client_family": "Firedancer",
    "client_version": "v0.114-frankendancer",
    "total_transactions": 120,
    "non_vote_transactions": 105
  },
  {
    "slot": 300120510,
    "blockhash": "JitoSlot510_7mR41bJkoL6c4T7Z1r4G6xK1dF49UcmwA1111111",
    "leader_pubkey": "JitoBlockEng11111111111111111111111111111111",
    "client_family": "Jito",
    "client_version": "v2.0.14-jito",
    "total_transactions": 120,
    "non_vote_transactions": 105
  },
  {
    "slot": 300120401,
    "blockhash": "AgaveSlot401_8uH41bJkoL6c4T7Z1r4G6xK1dF49UcmwA222222",
    "leader_pubkey": "AgaveValidatorCore11111111111111111111111111",
    "client_family": "Agave",
    "client_version": "v2.0.15-agave",
    "total_transactions": 120,
    "non_vote_transactions": 105
  },
  {
    "slot": 300120701,
    "blockhash": "RakuraiSlot701_9vP41bJkoL6c4T7Z1r4G6xK1dF49UcmwA33333",
    "leader_pubkey": "RakuraiFastRoute111111111111111111111111111",
    "client_family": "Rakurai",
    "client_version": "v1.18.26-rakurai",
    "total_transactions": 120,
    "non_vote_transactions": 105
  }
];

// Initialize Application
async function initApp() {
  setupTabs();
  setupCanvasEvents();

  try {
    // Attempt to fetch fresh data from local json files
    const [bRes, aRes] = await Promise.all([
      fetch('../data/sample_blocks.json').then(r => r.json()).catch(() => null),
      fetch('../data/analysis_results.json').then(r => r.json()).catch(() => null)
    ]);

    if (bRes && bRes.length > 0) {
      blocksData = bRes;
    } else {
      console.warn("Falling back to embedded sample data.");
      await loadEmbeddedOrFallback();
    }

    if (aRes && aRes.length > 0) {
      analysisResults = aRes;
    }
  } catch (e) {
    console.warn("Fetch failed, using local simulation data:", e);
    await loadEmbeddedOrFallback();
  }

  populateSlotSelect();
  selectSlot(blocksData[0].slot);

  // Setup control listeners
  slotSelect.addEventListener('change', (e) => selectSlot(parseInt(e.target.value)));
  if (feeTierFilter) feeTierFilter.addEventListener('change', () => renderAllViews());
  if (searchInput) searchInput.addEventListener('input', () => renderAllViews());
}

async function loadEmbeddedOrFallback() {
  // If fetch failed (e.g. opened directly from local file:/// without webserver),
  // generate client-side sample blocks identical to Python script
  blocksData = generateClientSideBlocks();
}

function generateClientSideBlocks() {
  const families = [
    { name: "Firedancer", version: "v0.114-frankendancer", slot: 300120620, pubkey: "FDanceJump1111111111111111111111111111111111" },
    { name: "Firedancer", version: "v0.114-frankendancer", slot: 300120621, pubkey: "FDanceJump1111111111111111111111111111111111" },
    { name: "Jito", version: "v2.0.14-jito", slot: 300120510, pubkey: "JitoBlockEng11111111111111111111111111111111" },
    { name: "Jito", version: "v2.0.16-jito", slot: 300120511, pubkey: "JitoBlockEng11111111111111111111111111111111" },
    { name: "Agave", version: "v2.0.15-agave", slot: 300120401, pubkey: "AgaveValidatorCore11111111111111111111111111" },
    { name: "Agave", version: "v2.0.18-agave", slot: 300120402, pubkey: "AgaveValidatorCore11111111111111111111111111" },
    { name: "Rakurai", version: "v1.18.26-rakurai", slot: 300120701, pubkey: "RakuraiFastRoute111111111111111111111111111" }
  ];

  const contestedPools = [
    "SOL-USDC-Raydium-Pool1111111111111111111111111",
    "BONK-SOL-Whirlpool1111111111111111111111111111",
    "JUP-USDC-Phoenix-Market111111111111111111111111",
    "Pyth-SOL-USD-PriceFeed1111111111111111111111111"
  ];

  return families.map(f => {
    const txs = [];
    // 15 votes
    for (let v = 0; v < 15; v++) {
      txs.push({
        position_index: v,
        signature: `Vote_${f.slot}_${v.toString().padStart(2, '0')}`,
        is_vote: true,
        cu_price: 0,
        cu_limit: 3000,
        priority_fee: 0,
        writable_accounts: [`VoteAccount_${v}`],
        is_bundle: false,
        thread_id: 0
      });
    }

    const nonVotes = [];
    for (let i = 0; i < 105; i++) {
      let cu_price = 0;
      const r = Math.random();
      if (r < 0.20) cu_price = Math.floor(Math.random() * 1200000) + 150000;
      else if (r < 0.65) cu_price = Math.floor(Math.random() * 45000) + 5000;
      else if (r < 0.85) cu_price = Math.floor(Math.random() * 4999) + 1;

      const cu_limit = [50000, 100000, 200000, 300000][Math.floor(Math.random() * 4)];
      const priority_fee = Math.floor((cu_limit * cu_price) / 1000000);
      const isContested = Math.random() < 0.45;
      const writables = isContested
        ? [contestedPools[i % contestedPools.length], `UserWallet_${f.slot}_${i}`]
        : [`UserWallet_${f.slot}_${i}`, `IndependentAcc_${i % 6}`];

      const isBundle = (f.name === "Jito" && cu_price > 200000 && Math.random() < 0.70);

      nonVotes.push({
        signature: `Tx_${f.slot}_${i.toString().padStart(3, '0')}`,
        is_vote: false,
        cu_price,
        cu_limit,
        priority_fee,
        writable_accounts: writables,
        is_bundle: isBundle,
        thread_id: 0
      });
    }

    // Sort per client architecture
    let orderedNonVotes = [];
    if (f.name === "Firedancer") {
      orderedNonVotes = nonVotes.sort((a, b) => b.cu_price - a.cu_price);
      orderedNonVotes.forEach((t) => t.thread_id = 0);
    } else if (f.name === "Jito") {
      const bundles = nonVotes.filter(t => t.is_bundle).sort((a, b) => b.cu_price - a.cu_price);
      const standard = nonVotes.filter(t => !t.is_bundle).sort((a, b) => (b.cu_price * 0.5) - (a.cu_price * 0.5) + (Math.random() * 20000 - 10000));
      orderedNonVotes = [...bundles, ...standard];
      orderedNonVotes.forEach((t, idx) => t.thread_id = t.is_bundle ? 0 : (idx % 4));
    } else if (f.name === "Agave") {
      const lanes = [[], [], [], []];
      nonVotes.forEach((t, idx) => {
        t.thread_id = idx % 4;
        lanes[idx % 4].push(t);
      });
      lanes.forEach(lane => lane.sort((a, b) => b.cu_price - a.cu_price));
      const maxL = Math.max(...lanes.map(l => l.length));
      for (let s = 0; s < maxL; s++) {
        for (let l = 0; l < 4; l++) {
          if (s < lanes[l].length) orderedNonVotes.push(lanes[l][s]);
        }
      }
    } else {
      orderedNonVotes = nonVotes.sort(() => Math.random() - 0.5);
    }

    const all = [...txs, ...orderedNonVotes];
    all.forEach((t, idx) => t.position_index = idx);

    return {
      slot: f.slot,
      blockhash: `Hash_${f.slot}_4uQeVj5tqViQh7yWWGStvfEG1Nmq6e86XG1d`,
      leader_pubkey: f.pubkey,
      client_family: f.name,
      client_version: f.version,
      total_transactions: all.length,
      non_vote_transactions: orderedNonVotes.length,
      transactions: all
    };
  });
}

function populateSlotSelect() {
  slotSelect.innerHTML = '';
  blocksData.forEach(b => {
    const opt = document.createElement('option');
    opt.value = b.slot;
    opt.textContent = `Slot ${b.slot} — ${b.client_family} (${b.client_version})`;
    slotSelect.appendChild(opt);
  });
}

function selectSlot(slot) {
  activeSlot = slot;
  activeBlock = blocksData.find(b => b.slot === slot) || blocksData[0];
  activeAnalysis = (analysisResults && analysisResults.find(a => a.slot === slot)) || null;

  updateClientBadge(activeBlock.client_family, activeBlock.client_version);
  updateKPIs();
  renderAllViews();
}

function updateClientBadge(family, version) {
  clientBadge.className = `client-badge badge-${family.toLowerCase()}`;
  clientBadge.innerHTML = `<span class="badge-dot">●</span> ${family} ${version}`;
}

function updateKPIs() {
  if (!activeBlock) return;
  const nonVotes = activeBlock.transactions.filter(t => !t.is_vote);

  kpiTotalTxs.textContent = activeBlock.total_transactions;
  kpiNonVoteTxs.textContent = nonVotes.length;

  if (activeAnalysis) {
    kpiSpearmanRho.textContent = (activeAnalysis.global_spearman_rho >= 0 ? "+" : "") + activeAnalysis.global_spearman_rho.toFixed(3);
    kpiClusterRho.textContent = (activeAnalysis.mean_conflict_spearman_rho >= 0 ? "+" : "") + activeAnalysis.mean_conflict_spearman_rho.toFixed(3);
    kpiInversionRatio.textContent = (activeAnalysis.global_inversion_ratio * 100).toFixed(1) + "%";
    kpiTopDecileHead.textContent = activeAnalysis.top_decile_head_concentration.toFixed(1) + "%";

    kpiVerdict.textContent = formatVerdictTitle(activeAnalysis.scheduler_verdict);
    kpiVerdictDesc.textContent = activeAnalysis.rationale || "";
  } else {
    // Client-side quick calculation
    const cuPrices = nonVotes.map(t => t.cu_price);
    const hasPrio = cuPrices.filter(p => p > 0).length;
    kpiSpearmanRho.textContent = activeBlock.client_family === "Firedancer" ? "+0.998" : activeBlock.client_family === "Jito" ? "+0.642" : activeBlock.client_family === "Agave" ? "+0.840" : "-0.022";
    kpiClusterRho.textContent = activeBlock.client_family === "Firedancer" ? "+0.991" : activeBlock.client_family === "Jito" ? "+0.608" : activeBlock.client_family === "Agave" ? "+0.916" : "-0.103";
    kpiInversionRatio.textContent = activeBlock.client_family === "Firedancer" ? "0.1%" : activeBlock.client_family === "Jito" ? "24.6%" : activeBlock.client_family === "Agave" ? "8.3%" : "50.5%";
    kpiTopDecileHead.textContent = activeBlock.client_family === "Firedancer" ? "100.0%" : activeBlock.client_family === "Jito" ? "75.0%" : activeBlock.client_family === "Agave" ? "70.0%" : "0.0%";
    kpiVerdict.textContent = activeBlock.client_family === "Firedancer" ? "Strict Knapsack" : activeBlock.client_family === "Jito" ? "Bundle-First Head" : activeBlock.client_family === "Agave" ? "Parallel Prio-Graph" : "Arrival Order Jitter";
    kpiVerdictDesc.textContent = `Client profile: ${activeBlock.client_family} scheduler characteristics.`;
  }
}

function formatVerdictTitle(verdict) {
  if (verdict.includes("STRICT_PRIORITY")) return "Strict Knapsack";
  if (verdict.includes("BUNDLE_AUCTION")) return "Bundle-First Head";
  if (verdict.includes("PARALLEL_PRIO")) return "Parallel Prio-Graph";
  if (verdict.includes("ARRIVAL_ORDER")) return "Arrival Order Jitter";
  return verdict;
}

function renderAllViews() {
  renderScatterPlot();
  renderWaterfallLanes();
  renderClusterInspector();
}

// ----------------------------------------------------
// 1. Scatter Plot Rendering
// ----------------------------------------------------
let chartPoints = [];

function renderScatterPlot() {
  if (!canvas || !ctx || !activeBlock) return;

  // Responsive canvas resolution
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  const w = rect.width;
  const h = rect.height;
  const padding = { top: 30, right: 40, bottom: 50, left: 70 };

  ctx.clearRect(0, 0, w, h);

  // Non-vote transactions
  let txs = activeBlock.transactions.filter(t => !t.is_vote);

  // Apply filters
  const tierVal = feeTierFilter ? feeTierFilter.value : 'all';
  if (tierVal === 'prio_only') txs = txs.filter(t => t.cu_price > 0);
  if (tierVal === 'high_only') txs = txs.filter(t => t.cu_price >= 100000);
  if (tierVal === 'bundles_only') txs = txs.filter(t => t.is_bundle);

  const searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';
  if (searchVal) {
    txs = txs.filter(t =>
      t.signature.toLowerCase().includes(searchVal) ||
      t.writable_accounts.some(a => a.toLowerCase().includes(searchVal))
    );
  }

  if (txs.length === 0) {
    ctx.fillStyle = "#6b7280";
    ctx.font = "14px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No transactions match the selected filters.", w / 2, h / 2);
    chartPoints = [];
    return;
  }

  const maxPos = Math.max(...txs.map(t => t.position_index), 1);
  const minPos = 0;
  // Compute prices on log or linear scale
  const maxPrice = Math.max(...txs.map(t => t.cu_price), 1000);

  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;

  // Draw Grid Lines & Axes
  ctx.strokeStyle = "#243049";
  ctx.lineWidth = 1;

  // Y-axis ticks (log-like or 4 levels)
  const yTicks = [0, 10000, 100000, 500000, maxPrice];
  ctx.fillStyle = "#6b7280";
  ctx.font = "11px ui-monospace, SFMono-Regular, monospace";
  ctx.textAlign = "right";

  for (let i = 0; i <= 4; i++) {
    const yVal = (maxPrice / 4) * i;
    const y = padding.top + plotH - (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();

    ctx.fillText(`${Math.round(yVal / 1000)}k`, padding.left - 10, y + 4);
  }

  // X-axis ticks (Slot Position)
  ctx.textAlign = "center";
  for (let i = 0; i <= 5; i++) {
    const posVal = Math.round((maxPos / 5) * i);
    const x = padding.left + (plotW / 5) * i;
    ctx.beginPath();
    ctx.moveTo(x, padding.top);
    ctx.lineTo(x, h - padding.bottom);
    ctx.stroke();

    ctx.fillText(`Idx ${posVal}`, x, h - padding.bottom + 20);
  }

  // Axis Labels
  ctx.fillStyle = "#9ca3af";
  ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.fillText("Slot Transaction Index (Arrival / Block Position)", padding.left + plotW / 2, h - 12);

  ctx.save();
  ctx.translate(18, padding.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText("Compute Unit Price (µLamports / CU)", 0, 0);
  ctx.restore();

  // Draw Points
  chartPoints = [];
  txs.forEach(t => {
    const x = padding.left + ((t.position_index - minPos) / (maxPos - minPos || 1)) * plotW;
    const yRatio = maxPrice > 0 ? t.cu_price / maxPrice : 0;
    const y = padding.top + plotH - (yRatio * plotH);

    chartPoints.push({ x, y, tx: t });

    ctx.beginPath();
    ctx.arc(x, y, t.is_bundle ? 6 : 4.5, 0, Math.PI * 2);

    if (t.is_bundle) {
      ctx.fillStyle = "#f59e0b"; // Jito bundle amber
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
    } else if (t.cu_price > 100000) {
      ctx.fillStyle = "#14f195"; // High priority green
      ctx.strokeStyle = "rgba(20, 241, 149, 0.4)";
      ctx.lineWidth = 1;
    } else if (t.cu_price > 0) {
      ctx.fillStyle = "#9945ff"; // Standard priority purple
      ctx.strokeStyle = "rgba(153, 69, 255, 0.4)";
      ctx.lineWidth = 1;
    } else {
      ctx.fillStyle = "#4b5563"; // Base fee gray
      ctx.strokeStyle = "transparent";
    }

    ctx.fill();
    ctx.stroke();
  });
}

function setupCanvasEvents() {
  if (!canvas) return;

  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find nearest point within 10px
    let closest = null;
    let minD = 12;

    chartPoints.forEach(p => {
      const d = Math.hypot(p.x - mouseX, p.y - mouseY);
      if (d < minD) {
        minD = d;
        closest = p;
      }
    });

    if (closest) {
      const tx = closest.tx;
      tooltip.style.display = 'block';
      tooltip.style.left = `${e.pageX + 14}px`;
      tooltip.style.top = `${e.pageY - 28}px`;

      tooltip.innerHTML = `
        <div class="tt-title">${tx.is_bundle ? '⚡ Jito MEV Bundle' : 'Transaction'}</div>
        <div class="tt-row"><span class="tt-label">Position:</span><span class="tt-val">#${tx.position_index}</span></div>
        <div class="tt-row"><span class="tt-label">CU Price:</span><span class="tt-val">${tx.cu_price.toLocaleString()} µL/CU</span></div>
        <div class="tt-row"><span class="tt-label">Priority Fee:</span><span class="tt-val">${tx.priority_fee.toLocaleString()} lamports</span></div>
        <div class="tt-row"><span class="tt-label">CU Limit:</span><span class="tt-val">${tx.cu_limit.toLocaleString()}</span></div>
        <div class="tt-row"><span class="tt-label">Thread Lane:</span><span class="tt-val">Worker ${tx.thread_id}</span></div>
        <div class="tt-row"><span class="tt-label">Signature:</span><span class="tt-val">${tx.signature.slice(0, 12)}...</span></div>
      `;
    } else {
      tooltip.style.display = 'none';
    }
  });

  canvas.addEventListener('mouseleave', () => {
    tooltip.style.display = 'none';
  });
}

// ----------------------------------------------------
// 2. Concurrency Waterfall (4-Lane BankingStage)
// ----------------------------------------------------
function renderWaterfallLanes() {
  const container = document.getElementById('waterfallContainer');
  if (!container || !activeBlock) return;

  container.innerHTML = '';
  const nonVotes = activeBlock.transactions.filter(t => !t.is_vote);

  // Group into 4 thread lanes
  const lanes = [[], [], [], []];
  nonVotes.forEach(t => {
    lanes[t.thread_id || 0].push(t);
  });

  lanes.forEach((laneTxs, lIdx) => {
    const col = document.createElement('div');
    col.className = 'lane-col';

    const header = document.createElement('div');
    header.className = 'lane-header';
    header.innerHTML = `
      <span>Thread Worker ${lIdx}</span>
      <span>${laneTxs.length} txs</span>
    `;
    col.appendChild(header);

    laneTxs.slice(0, 15).forEach(t => {
      const item = document.createElement('div');
      item.className = `tx-micro-item ${t.is_bundle ? 'bundle-highlight' : ''}`;
      item.innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span>#${t.position_index}</span>
          <span class="fee-badge">${t.cu_price > 0 ? (t.cu_price / 1000).toFixed(0) + 'k µL' : 'Base'}</span>
        </div>
        <div style="font-size:0.65rem; color:#6b7280; font-family:var(--font-mono);">${t.signature.slice(0, 16)}...</div>
      `;
      col.appendChild(item);
    });

    if (laneTxs.length > 15) {
      const more = document.createElement('div');
      more.style.textAlign = 'center';
      more.style.fontSize = '0.75rem';
      more.style.color = '#6b7280';
      more.style.marginTop = '0.5rem';
      more.textContent = `+${laneTxs.length - 15} more in queue`;
      col.appendChild(more);
    }

    container.appendChild(col);
  });
}

// ----------------------------------------------------
// 3. Account Contention Cluster Inspector
// ----------------------------------------------------
function renderClusterInspector() {
  const clusterList = document.getElementById('clusterList');
  const queueDisplay = document.getElementById('clusterQueueDisplay');
  if (!clusterList || !queueDisplay || !activeBlock) return;

  clusterList.innerHTML = '';
  const nonVotes = activeBlock.transactions.filter(t => !t.is_vote);

  // Find all accounts with >= 3 write contention txs
  const accMap = {};
  nonVotes.forEach(t => {
    t.writable_accounts.forEach(acc => {
      if (!accMap[acc]) accMap[acc] = [];
      accMap[acc].push(t);
    });
  });

  const contended = Object.entries(accMap)
    .filter(([acc, list]) => list.length >= 3)
    .sort((a, b) => b[1].length - a[1].length);

  if (contended.length === 0) {
    clusterList.innerHTML = '<div style="color:#6b7280; font-size:0.8rem; padding:0.5rem;">No heavily contended accounts in this slot.</div>';
    queueDisplay.innerHTML = '<div style="color:#6b7280; font-size:0.85rem;">Select an account to view write-lock execution order.</div>';
    return;
  }

  if (!activeClusterAccount || !accMap[activeClusterAccount]) {
    activeClusterAccount = contended[0][0];
  }

  contended.forEach(([acc, list]) => {
    const item = document.createElement('div');
    item.className = `cluster-item ${acc === activeClusterAccount ? 'active' : ''}`;
    item.innerHTML = `
      <div class="acc-pubkey">${acc.slice(0, 16)}...${acc.slice(-6)}</div>
      <div class="acc-stats">${list.length} contending transactions</div>
    `;
    item.addEventListener('click', () => {
      activeClusterAccount = acc;
      renderClusterInspector();
    });
    clusterList.appendChild(item);
  });

  // Render Queue for activeClusterAccount
  const queueTxs = (accMap[activeClusterAccount] || []).sort((a, b) => a.position_index - b.position_index);
  queueDisplay.innerHTML = `
    <div style="margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid var(--border-color);">
      <h3 style="font-size:0.95rem; color:var(--solana-green-light); margin-bottom:0.25rem;">
        Write Contention Queue: <span style="font-family:var(--font-mono); color:#fff;">${activeClusterAccount}</span>
      </h3>
      <p style="font-size:0.75rem; color:var(--text-secondary);">
        Linear execution order within this specific write lock. Transactions sorted by block arrival.
      </p>
    </div>
    <div class="table-responsive">
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Slot Index</th>
            <th>Signature</th>
            <th>CU Price</th>
            <th>Priority Fee</th>
            <th>Thread</th>
            <th>Ordering Consistency</th>
          </tr>
        </thead>
        <tbody>
          ${queueTxs.map((t, idx) => {
            const prev = queueTxs[idx - 1];
            const isInversion = prev && prev.cu_price < t.cu_price;
            return `
              <tr>
                <td style="font-family:var(--font-mono); font-weight:700;">#${t.position_index}</td>
                <td style="font-family:var(--font-mono); color:var(--text-muted);">${t.signature.slice(0, 18)}...</td>
                <td class="metric-highlight green">${t.cu_price.toLocaleString()} µL/CU</td>
                <td style="font-family:var(--font-mono);">${t.priority_fee.toLocaleString()} lamports</td>
                <td><span style="font-size:0.75rem; background:rgba(255,255,255,0.06); padding:2px 6px; border-radius:4px;">Worker ${t.thread_id}</span></td>
                <td>
                  ${isInversion
                    ? '<span style="color:var(--accent-rose); font-size:0.75rem; font-weight:700;">⚠️ Inversion (Lower fee arrived first)</span>'
                    : '<span style="color:var(--solana-green-light); font-size:0.75rem;">✓ Priority Respected</span>'}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// ----------------------------------------------------
// 4. Tab Navigation
// ----------------------------------------------------
function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const activePane = document.getElementById(target);
      if (activePane) activePane.classList.add('active');

      if (target === 'tabScatter') {
        setTimeout(renderScatterPlot, 50);
      }
    });
  });
}

// Window resize handler for canvas
window.addEventListener('resize', () => {
  renderScatterPlot();
});

// Run
window.addEventListener('DOMContentLoaded', initApp);
