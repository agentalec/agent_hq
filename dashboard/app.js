/* Operator dashboard — reads the agent-hq-state branch and renders it.
 *
 * Implements `Operator Dashboard.dc.html` from the Claude Design project
 * against the real state documents (docs/dashboard-design-requirements.md).
 *
 * Two rules run through the whole file:
 *   1. Every string in the data is untrusted (issue text, block reasons,
 *      artifact paths written by agents). Nodes are built with
 *      createElement + textContent; there is no innerHTML anywhere, and no
 *      href is concatenated from state data without validating its shape.
 *   2. `cost_usd: null` / `usage_known: false` means UNMETERED, not free.
 *      Unmetered runs are excluded from every total and counted separately.
 */
(function () {
  'use strict';

  var META_REPO = document.querySelector('meta[name="agent-hq:engine-repo"]');
  var META_BRANCH = document.querySelector('meta[name="agent-hq:state-branch"]');
  var ENGINE_REPO = (META_REPO && META_REPO.content) || '';
  var STATE_BRANCH = (META_BRANCH && META_BRANCH.content) || 'agent-hq-state';
  var RAW = 'https://raw.githubusercontent.com/';
  var DATA_URL = RAW + ENGINE_REPO + '/' + STATE_BRANCH + '/dashboard.json';

  /* Served locally (`python3 -m http.server` in this directory), read the
     checked-in fixture instead of the live branch — see README.md. */
  var LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if (LOCAL) DATA_URL = 'fixture.json';

  /* Tone is chosen from this fixed map only — never from state data, so a
     hostile `state` string can't reach a style value. */
  var TONE = {
    DONE: 'var(--status-stable)', SUCCEEDED: 'var(--status-stable)',
    BLOCKED: 'var(--destructive)', FAILED: 'var(--destructive)',
    WAITING_GATE: 'var(--status-moderate)', AWAITING_MERGE: 'var(--status-moderate)',
    ACTIVE: 'var(--status-info)', RUNNING: 'var(--status-info)',
    QUEUED: 'var(--muted-foreground)',
    /* Withdrawn work, not failed work: an entry removed from the queue before
       it ran. Deliberately not `--destructive` — nothing went wrong. */
    CANCELLED: 'var(--muted-foreground)'
  };
  function tone(s) { return TONE[s] || 'var(--muted-foreground)'; }

  var STATUS_ORDER = ['ACTIVE', 'AWAITING_MERGE', 'BLOCKED', 'DONE'];

  /* ---- tiny DOM helpers -------------------------------------------------- */

  function el(tag, cls, txt) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined && txt !== null) node.textContent = String(txt);
    return node;
  }
  function toned(node, state) { node.style.setProperty('--tone', tone(state)); return node; }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function frag() { return document.createDocumentFragment(); }

  var SVG_NS = 'http://www.w3.org/2000/svg';
  function icon(size, paths) {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.75');
    svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('aria-hidden', 'true');
    paths.forEach(function (d) {
      var p = document.createElementNS(SVG_NS, 'path');
      p.setAttribute('d', d);
      svg.appendChild(p);
    });
    return svg;
  }
  var EXTERNAL = ['M15 3h6v6', 'M10 14 21 3', 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6'];

  /* ---- formatting -------------------------------------------------------- */

  function money(n) { return '$' + n.toFixed(2); }

  function parseTs(s) {
    if (typeof s !== 'string') return null;
    var t = Date.parse(s);
    return isNaN(t) ? null : t;
  }

  /* "2d 3h", "4h 12m", "51m", "40s" — the coarse two-unit form the design uses. */
  function duration(ms) {
    if (ms === null || ms === undefined || ms < 0) return '—';
    var s = Math.floor(ms / 1000);
    var d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
    var m = Math.floor((s % 3600) / 60);
    if (d) return d + 'd ' + h + 'h';
    if (h) return h + 'h ' + m + 'm';
    if (m) return m + 'm';
    return s + 's';
  }
  /* "10 minutes ago", "yesterday", "3 days ago" — Intl does the pluralising
     and the unit choice, so there is no hand-rolled table to drift. */
  var RTF = typeof Intl !== 'undefined' && Intl.RelativeTimeFormat
    ? new Intl.RelativeTimeFormat('en', { numeric: 'auto' }) : null;
  var UNITS = [
    ['year', 31536000000], ['month', 2592000000], ['week', 604800000],
    ['day', 86400000], ['hour', 3600000], ['minute', 60000], ['second', 1000]
  ];

  function relative(iso) {
    var t = parseTs(iso);
    if (t === null) return '';
    var diff = t - Date.now();
    if (!RTF) return duration(Math.abs(diff)) + (diff < 0 ? ' ago' : ' from now');
    for (var i = 0; i < UNITS.length; i++) {
      if (Math.abs(diff) >= UNITS[i][1] || UNITS[i][0] === 'second') {
        return RTF.format(Math.round(diff / UNITS[i][1]), UNITS[i][0]);
      }
    }
    return '';
  }

  /* A timestamped label that keeps the exact value in the tooltip: relative
     time is for scanning, the ISO string is what you paste into a log grep. */
  function stamped(cls, prefix, iso) {
    var node = el('span', cls, iso ? prefix + relative(iso) : prefix + 'unknown');
    if (iso) node.title = iso;
    return node;
  }

  function ago(iso) {
    return parseTs(iso) === null ? '' : '· ' + relative(iso);
  }
  function shortRun(id) { return typeof id === 'string' ? id.slice(0, 8) : '—'; }

  /* ---- URL builders (every one validates before it trusts) --------------- */

  var REPO_RE = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;
  var PR_RE = /^([A-Za-z0-9._-]+\/[A-Za-z0-9._-]+)#(\d+)$/;
  var TICKET_RE = /^[A-Za-z0-9._-]+$/;

  function prUrl(ref) {
    var m = typeof ref === 'string' ? ref.match(PR_RE) : null;
    return m ? 'https://github.com/' + m[1] + '/pull/' + m[2] : null;
  }
  function issueUrl(repo, ticketId) {
    if (!REPO_RE.test(repo || '') || !TICKET_RE.test(String(ticketId))) return null;
    // Ticket ids are engine-repo issue numbers; a non-numeric id (fixtures use
    // "HQ-1") has no issue to link to.
    return /^\d+$/.test(String(ticketId))
      ? 'https://github.com/' + repo + '/issues/' + ticketId : null;
  }
  function safeRelPath(path) {
    if (typeof path !== 'string' || !path) return null;
    // Reject anything that isn't a plain relative path: a scheme, a
    // protocol-relative prefix, or a traversal segment.
    if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(path) || path.indexOf('//') === 0) return null;
    var segs = path.split('/');
    for (var i = 0; i < segs.length; i++) if (segs[i] === '..') return null;
    return segs;
  }

  function artifactBase(ticketId, runId) {
    if (!REPO_RE.test(ENGINE_REPO)) return null;
    if (!TICKET_RE.test(String(ticketId)) || !TICKET_RE.test(String(runId || ''))) return null;
    return RAW + ENGINE_REPO + '/' + STATE_BRANCH + '/tickets/' +
      encodeURIComponent(ticketId) + '/artifacts/' + encodeURIComponent(runId) + '/';
  }

  function artifactUrl(ticketId, runId, path) {
    var base = artifactBase(ticketId, runId);
    var segs = safeRelPath(path);
    if (!base || !segs) return null;
    return base + segs.map(encodeURIComponent).join('/');
  }

  var MARKDOWN_EXT = /\.(md|markdown)$/i;
  var IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|avif)$/i;
  var TEXT_EXT = /\.(txt|log|json|ya?ml|diff|patch|csv|ini|toml|ts|tsx|js|jsx|py|sh|css|html?)$/i;

  function artifactKind(path) {
    if (MARKDOWN_EXT.test(path)) return 'markdown';
    if (IMAGE_EXT.test(path)) return 'image';
    if (TEXT_EXT.test(path)) return 'text';
    return 'opaque';
  }

  /* ---- model ------------------------------------------------------------- */

  function runsOf(t) { return Array.isArray(t.runs) ? t.runs : []; }
  function metered(run) {
    return run.usage_known === true && typeof run.cost_usd === 'number';
  }

  /* Effective queue position: `queue_seq` where a run carries one, else its
     array index — the same fallback the engine uses (`queue_positions`), so a
     ticket written before the field keeps exactly the order dispatch gave it. */
  function queuePos(run, index) {
    return typeof run.queue_seq === 'number' ? run.queue_seq : index;
  }

  /* One step per (parent_run_id, handoff_key); `attempt` is the retry axis
     inside it — a retry reuses the key at a higher attempt.

     Ordered by QUEUE POSITION, not chain depth and not array order. Depth
     stopped being an ordering axis once one run could declare several entries:
     they all sit at the declaring run's depth + 1, so depth ties and the
     tiebreak decided everything. Array order is wrong for a different reason —
     a retry inherits the position of the attempt it replaces, so it can belong
     EARLIER in the queue than a run appended after that attempt failed. */
  function steps(ticket) {
    var groups = {}, order = [];
    runsOf(ticket).forEach(function (run, index) {
      var key = (run.parent_run_id || '') + ' ' + (run.handoff_key || '');
      var pos = queuePos(run, index);
      if (!groups[key]) {
        groups[key] = {
          key: key, task: run.task_id, parent: run.parent_run_id || null,
          handoffKey: run.handoff_key || null,
          depth: typeof run.chain_depth === 'number' ? run.chain_depth : 0,
          pos: pos, attempts: []
        };
        order.push(groups[key]);
      }
      var g = groups[key];
      g.depth = Math.min(g.depth, typeof run.chain_depth === 'number' ? run.chain_depth : g.depth);
      g.pos = Math.min(g.pos, pos);
      g.attempts.push(run);
    });
    order.forEach(function (g) {
      g.attempts.sort(function (a, b) { return (a.attempt || 0) - (b.attempt || 0); });
      g.last = g.attempts[g.attempts.length - 1];
      g.state = g.last ? g.last.state : 'QUEUED';
      /* Which run this one READ from is not who enqueued it — one run can
         declare several entries, so the enqueuer of `review` need not be the
         producer of what `review` consumed. */
      g.inputFrom = g.last && g.last.input_from_run_id ? g.last.input_from_run_id : null;
    });
    order.sort(function (a, b) { return a.pos - b.pos; });
    return order;
  }

  function model(data) {
    var tickets = Array.isArray(data.tickets) ? data.tickets : [];
    var repo = REPO_RE.test(data.engine_repo || '') ? data.engine_repo : ENGINE_REPO;
    var gates = [], running = [], meteredRuns = 0, unmeteredRuns = 0, total = 0;
    var byTask = {}, byBinding = {};

    tickets.forEach(function (t) {
      runsOf(t).forEach(function (run) {
        if (metered(run)) {
          meteredRuns++; total += run.cost_usd;
          byTask[run.task_id] = (byTask[run.task_id] || 0) + run.cost_usd;
        } else {
          unmeteredRuns++;
        }
        var binding = 'agent-session/' + ((run.bindings && run.bindings['agent-session']) || 'unbound');
        var b = byBinding[binding] || (byBinding[binding] = { label: binding, runs: 0, cost: 0, metered: 0 });
        b.runs++;
        if (metered(run)) { b.cost += run.cost_usd; b.metered++; }

        if (run.state === 'WAITING_GATE') gates.push({ ticket: t, run: run });
        if (run.state === 'RUNNING') running.push(run);
      });
    });

    gates.sort(function (a, b) {
      return (parseTs(a.run.gate_requested_at) || Infinity) - (parseTs(b.run.gate_requested_at) || Infinity);
    });

    var blocked = tickets.filter(function (t) { return t.status === 'BLOCKED'; });
    return {
      repo: repo, tickets: tickets, gates: gates, running: running, blocked: blocked,
      health: (data.health && typeof data.health === 'object') ? data.health : {},
      spend: {
        total: total, meteredRuns: meteredRuns, unmeteredRuns: unmeteredRuns,
        byTask: Object.keys(byTask).sort().map(function (k) { return { label: k, value: byTask[k] }; }),
        byBinding: Object.keys(byBinding).sort().map(function (k) { return byBinding[k]; })
      }
    };
  }

  /* ---- sections ---------------------------------------------------------- */

  function renderAttention(m) {
    var host = clear(document.getElementById('attention'));
    var noReason = m.blocked.filter(function (t) { return !t.block_reason; }).length;
    var nextDeadline = m.running
      .map(function (r) { return parseTs(r.deadline); })
      .filter(function (t) { return t !== null; })
      .sort(function (a, b) { return a - b; })[0];

    [
      { n: m.gates.length, label: 'WAITING_GATE', state: 'WAITING_GATE',
        detail: m.gates.length === 1 ? 'run paused on a human decision' : 'runs paused on a human decision' },
      { n: m.blocked.length, label: 'BLOCKED', state: 'BLOCKED',
        detail: noReason
          ? 'tickets stopped; ' + noReason + (noReason === 1 ? ' carries' : ' carry') + ' no block_reason'
          : 'tickets stopped' },
      { n: m.running.length, label: 'RUNNING', state: 'RUNNING',
        detail: !nextDeadline ? 'runs in flight'
          : nextDeadline < Date.now() ? 'in flight, past the deadline by ' + duration(Date.now() - nextDeadline)
          : 'in flight, next deadline in ' + duration(nextDeadline - Date.now()) }
    ].forEach(function (k) {
      var card = toned(el('div', 'kpi'), k.state);
      card.appendChild(el('span', 'kpi-n', k.n));
      card.appendChild(el('span', 'kpi-label', k.label));
      card.appendChild(el('span', 'kpi-detail', k.detail));
      host.appendChild(card);
    });
  }

  function renderGates(m) {
    var host = clear(document.getElementById('gates'));
    if (!m.gates.length) {
      var empty = el('div', 'state-card');
      empty.style.setProperty('--tone', 'var(--status-stable)');
      empty.appendChild(el('span', 'kind', 'CLEAR'));
      empty.appendChild(el('span', 'headline', 'No run is waiting on a human.'));
      empty.appendChild(el('span', 'body', 'A run appears here when it parks at WAITING_GATE — the engine asks for the decision on the ticket issue, or on the work-repo PR when the task binds to the pr-review gate.'));
      host.appendChild(empty);
      return;
    }

    m.gates.forEach(function (g) {
      var run = g.run, ticket = g.ticket;
      var requested = parseTs(run.gate_requested_at);
      var waitedMs = requested === null ? null : Date.now() - requested;
      // Over a day waiting reads as stuck, not merely pending.
      var waitState = (waitedMs !== null && waitedMs > 86400000) ? 'BLOCKED' : 'WAITING_GATE';

      var row = el('div', 'gate-row');

      var waited = toned(el('div', 'gate-waited'), waitState);
      waited.appendChild(el('span', 'n', waitedMs === null ? '—' : duration(waitedMs)));
      waited.appendChild(el('span', 'label', 'waiting'));
      row.appendChild(waited);

      var body = el('div', 'gate-body');
      var ids = el('div', 'gate-ids');
      ids.appendChild(el('span', 'ticket-ref', '#' + ticket.ticket_id));
      ids.appendChild(el('span', 'chip', run.task_id));
      ids.appendChild(toned(el('span', 'chip-state', 'WAITING_GATE'), 'WAITING_GATE'));
      ids.appendChild(el('span', 'gate-meta', shortRun(run.run_id)));
      body.appendChild(ids);

      var gateBinding = (run.bindings && run.bindings.gate) || '';
      var prRef = firstPrRef(ticket);
      var onPr = gateBinding === 'pr-review' && prRef;
      body.appendChild(el('span', 'pretty',
        onPr
          ? 'Task ' + run.task_id + ' is waiting on a review decision on the work-repo PR.'
          : 'Task ' + run.task_id + ' is waiting on an authorized /agent-hq decision on the ticket issue.'));
      var meta = el('span', 'gate-meta',
        'gate_request_id ' + (run.gate_request_id === undefined ? '—' : run.gate_request_id) +
        ' · requested ' + (run.gate_requested_at ? relative(run.gate_requested_at) : '—'));
      if (run.gate_requested_at) meta.title = run.gate_requested_at;
      body.appendChild(meta);
      row.appendChild(body);

      var href = onPr ? prUrl(prRef) : issueUrl(m.repo, ticket.ticket_id);
      if (href) {
        var link = el('a', 'btn btn-primary', onPr ? 'Open PR' : 'Open issue');
        link.href = href;
        link.rel = 'noopener';
        link.appendChild(icon(14, EXTERNAL));
        row.appendChild(link);
      } else {
        row.appendChild(el('span', 'gate-meta', 'no link — decide in the engine repo'));
      }
      host.appendChild(row);
    });
  }

  function firstPrRef(ticket) {
    var repos = Array.isArray(ticket.work_repos) ? ticket.work_repos : [];
    for (var i = 0; i < repos.length; i++) if (repos[i].pr_ref) return repos[i].pr_ref;
    return null;
  }

  function renderBoard(m, selectedId) {
    var host = clear(document.getElementById('board'));
    document.getElementById('board-count').textContent =
      m.tickets.length + (m.tickets.length === 1 ? ' ticket' : ' tickets') + ' on the state branch';

    if (!m.tickets.length) {
      var empty = el('div', 'state-card');
      empty.style.setProperty('--tone', 'var(--muted-foreground)');
      empty.appendChild(el('span', 'kind', 'EMPTY'));
      empty.appendChild(el('span', 'headline', 'No tickets on the state branch.'));
      empty.appendChild(el('span', 'body', 'A ticket appears here once an issue in the engine repo is labelled hq:intake and the engine has accepted it.'));
      var link = el('a', 'ticket-card-note', 'Open the engine repo');
      var url = REPO_RE.test(m.repo) ? 'https://github.com/' + m.repo + '/issues' : null;
      if (url) { link.href = url; link.rel = 'noopener'; empty.appendChild(link); }
      host.appendChild(empty);
      return;
    }

    // Columns come from the data, not a hardcoded list: AWAITING_MERGE was
    // added after this view was designed, and the next status would be too.
    var present = {};
    m.tickets.forEach(function (t) { present[t.status] = true; });
    var statuses = STATUS_ORDER.filter(function (s) { return present[s]; })
      .concat(Object.keys(present).filter(function (s) { return STATUS_ORDER.indexOf(s) === -1; }).sort());

    statuses.forEach(function (status) {
      var inCol = m.tickets.filter(function (t) { return t.status === status; });
      var col = el('div', 'board-col');
      var head = el('div', 'board-col-head');
      head.appendChild(toned(el('span', 'dot'), status));
      head.appendChild(el('span', 'board-col-status', status));
      head.appendChild(el('span', 'board-col-count', inCol.length));
      col.appendChild(head);
      inCol.forEach(function (t) { col.appendChild(ticketCard(t, selectedId)); });
      host.appendChild(col);
    });
  }

  function ticketCard(t, selectedId) {
    var runs = runsOf(t);
    var last = runs[runs.length - 1];
    var repos = Array.isArray(t.work_repos) ? t.work_repos : [];
    var prRef = firstPrRef(t);

    var card = el('a', 'ticket-card');
    card.href = '?ticket=' + encodeURIComponent(t.ticket_id);
    if (String(t.ticket_id) === String(selectedId)) card.setAttribute('aria-current', 'true');

    var top = el('div', 'ticket-card-top');
    top.appendChild(el('span', 'ticket-ref', '#' + t.ticket_id));
    top.appendChild(toned(el('span', 'chip-state', t.status), t.status));
    card.appendChild(top);

    var meta = el('div', 'ticket-card-meta');
    meta.appendChild(el('span', 'anywhere', repos.length ? repos[0].repo : 'no work repo'));
    meta.appendChild(el('span', null, '·'));
    meta.appendChild(el('span', null, runs.length + (runs.length === 1 ? ' run' : ' runs')));
    card.appendChild(meta);

    if (last) {
      var lastRow = el('div', 'ticket-card-last');
      lastRow.appendChild(el('span', 'chip', last.task_id));
      lastRow.appendChild(toned(el('span', 'state', last.state), last.state));
      if (last.attempt_started_at) {
        lastRow.appendChild(stamped('ticket-card-note', 'started ', last.attempt_started_at));
      }
      card.appendChild(lastRow);
    }

    var note = t.block_reason ? 'block_reason: ' + t.block_reason
      : prRef ? 'PR ' + prRef
      : last && last.handoff_key ? 'handoff_key ' + last.handoff_key
      : 'handoff_key absent — root run';
    card.appendChild(el('span', 'ticket-card-note', note));
    return card;
  }

  function renderSpend(m) {
    var s = m.spend;
    document.getElementById('spend-total').textContent = money(s.total);
    document.getElementById('spend-metered').textContent =
      'across ' + s.meteredRuns + (s.meteredRuns === 1 ? ' metered run' : ' metered runs');

    var notice = document.getElementById('spend-unmetered');
    var noticeText = document.getElementById('spend-unmetered-text');
    clear(noticeText);
    if (s.unmeteredRuns) {
      notice.hidden = false;
      noticeText.appendChild(document.createTextNode(s.unmeteredRuns + ' runs report '));
      noticeText.appendChild(el('span', 'mono', 'usage_known: false'));
      noticeText.appendChild(document.createTextNode(
        ' — unmetered, not free. Their real cost is unknown and excluded from every figure here.'));
    } else {
      notice.hidden = true;
    }

    var taskHost = clear(document.getElementById('spend-by-task'));
    var max = s.byTask.reduce(function (a, r) { return Math.max(a, r.value); }, 0);
    if (!s.byTask.length) {
      taskHost.appendChild(el('span', 'section-note', 'No metered run yet.'));
    }
    s.byTask.forEach(function (r) {
      var row = toned(el('div', 'bar-row'), 'RUNNING');
      row.appendChild(el('span', 'label', r.label));
      var track = el('span', 'bar-track');
      var fill = el('span', 'bar-fill');
      fill.style.width = (max > 0 ? Math.round((r.value / max) * 100) : 0) + '%';
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el('span', 'value', money(r.value)));
      taskHost.appendChild(row);
    });

    var bindHost = clear(document.getElementById('spend-by-binding'));
    s.byBinding.forEach(function (b) {
      var row = el('div', 'split-row');
      row.style.setProperty('--tone', b.metered ? 'var(--foreground)' : 'var(--status-moderate)');
      row.appendChild(el('span', 'label', b.label));
      var right = el('span', 'right');
      right.appendChild(el('span', 'runs', b.runs + (b.runs === 1 ? ' run' : ' runs')));
      right.appendChild(el('span', 'value', b.metered ? money(b.cost) : 'unmetered'));
      row.appendChild(right);
      bindHost.appendChild(row);
    });
  }

  function renderHealth(m) {
    var host = clear(document.getElementById('health'));
    var keys = Object.keys(m.health).sort();
    if (!keys.length) {
      host.appendChild(el('span', 'section-note',
        'No adapter health recorded yet — health is written when a run exercises an adapter.'));
      return;
    }
    keys.forEach(function (key) {
      var h = m.health[key] || {};
      var row = el('div', 'health-row');
      var left = el('div', 'health-key');
      left.appendChild(el('span', 'k', key));
      left.appendChild(el('span', 'd', h.detail === undefined ? '' : h.detail));
      row.appendChild(left);
      var right = el('div', 'health-state');
      var state = h.ok === true ? 'SUCCEEDED' : h.ok === false ? 'FAILED' : 'QUEUED';
      right.appendChild(toned(el('span', 'chip-state', h.ok === true ? 'ok' : h.ok === false ? 'failing' : 'unknown'), state));
      right.appendChild(stamped('ts', '', h.ts));
      row.appendChild(right);
      host.appendChild(row);
    });
  }

  /* ---- ticket detail ----------------------------------------------------- */

  function renderDetail(m, selectedId) {
    var host = clear(document.getElementById('detail'));
    var ticket = null;
    for (var i = 0; i < m.tickets.length; i++) {
      if (String(m.tickets[i].ticket_id) === String(selectedId)) { ticket = m.tickets[i]; break; }
    }

    if (!ticket) {
      var placeholder = el('div', 'state-card');
      placeholder.style.setProperty('--tone', 'var(--muted-foreground)');
      placeholder.appendChild(el('span', 'kind', selectedId ? 'NOT FOUND' : 'NO TICKET SELECTED'));
      placeholder.appendChild(el('span', 'headline', selectedId
        ? 'No ticket ' + selectedId + ' on the state branch.'
        : 'Pick a ticket from the board.'));
      placeholder.appendChild(el('span', 'body',
        'Full run history opens here: the chain via parent_run_id and handoff_key, attempts grouped per step, artifacts, PRs and cost. The URL is the permalink — paste it into Slack.'));
      host.appendChild(placeholder);
      return;
    }

    var runs = runsOf(ticket);
    var stepList = steps(ticket);

    var head = el('div', 'detail-head');
    var titleRow = el('div', 'detail-title-row');
    var title = el('div', 'detail-title');
    var h2 = el('h2', 'ds-h2', '#' + ticket.ticket_id);
    h2.id = 'hd-detail';
    title.appendChild(h2);
    title.appendChild(toned(el('span', 'chip-state', ticket.status), ticket.status));
    /* The ticket issue is where every human decision is actually made, so the
       detail view links to it. Null for a non-numeric id (see issueUrl), and
       the heading stays plain text rather than becoming a dead link. */
    var issueHref = issueUrl(m.repo, ticket.ticket_id);
    if (issueHref) {
      var issueLink = el('a', 'pr', 'Open issue');
      issueLink.href = issueHref;
      issueLink.rel = 'noopener';
      issueLink.appendChild(icon(12, EXTERNAL));
      title.appendChild(issueLink);
    }
    titleRow.appendChild(title);

    var close = el('button', 'icon-btn');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close ticket detail');
    close.appendChild(icon(14, ['M18 6 6 18', 'm6 6 12 12']));
    close.addEventListener('click', function () { select(null); });
    titleRow.appendChild(close);
    head.appendChild(titleRow);

    var facts = el('div', 'detail-facts');
    facts.appendChild(el('span', null, runs.length + (runs.length === 1 ? ' run' : ' runs')));
    facts.appendChild(el('span', null, '·'));
    facts.appendChild(el('span', null, stepList.length + (stepList.length === 1 ? ' step' : ' steps')));
    if (ticket.pinned_comment_id !== undefined) {
      facts.appendChild(el('span', null, '·'));
      facts.appendChild(el('span', null, 'pinned_comment_id ' + ticket.pinned_comment_id));
    }
    head.appendChild(facts);

    var permalink = el('div', 'detail-permalink');
    permalink.appendChild(el('span', 'anywhere', location.href));
    head.appendChild(permalink);

    if (ticket.block_reason) {
      var blocked = el('div', 'notice');
      blocked.style.setProperty('--tone', 'var(--destructive)');
      blocked.appendChild(el('span', 'pretty', 'block_reason: ' + ticket.block_reason));
      head.appendChild(blocked);
    }
    host.appendChild(head);

    var repos = Array.isArray(ticket.work_repos) ? ticket.work_repos : [];
    if (repos.length) {
      var repoStack = el('div', 'stack');
      repoStack.appendChild(el('span', 'stack-label', 'Work repos'));
      repos.forEach(function (r) {
        var card = el('div', 'repo-card');
        card.appendChild(el('span', 'name', r.repo));
        card.appendChild(el('span', 'branch',
          (r.branch || '—') + ' → ' + (r.base_branch || '—') +
          ' · ' + (r.recorded_head ? String(r.recorded_head).slice(0, 7) : 'no recorded head')));
        var href = prUrl(r.pr_ref);
        if (href) {
          var a = el('a', 'pr', r.pr_ref);
          a.href = href; a.rel = 'noopener';
          a.appendChild(icon(12, EXTERNAL));
          card.appendChild(a);
        }
        repoStack.appendChild(card);
      });
      host.appendChild(repoStack);
    }

    var chain = el('div', 'stack');
    var chainHead = el('div', 'card-head');
    chainHead.appendChild(el('span', 'stack-label', 'Run chain'));
    chainHead.appendChild(el('span', 'section-note pretty',
      'One step per (parent_run_id, handoff_key); attempts nested inside. '
      + 'Queue order (queue_seq) — neither runs-array order nor chain depth.'));
    chain.appendChild(chainHead);
    stepList.forEach(function (s) { chain.appendChild(stepNode(ticket, s)); });
    host.appendChild(chain);
  }

  function stepNode(ticket, s) {
    var wrap = el('div', 'step');
    var rail = el('div', 'step-rail');
    rail.appendChild(toned(el('span', 'dot'), s.state));
    rail.appendChild(el('span', 'line'));
    wrap.appendChild(rail);

    var body = el('div', 'step-body');
    var title = el('div', 'step-title');
    title.appendChild(el('span', 'step-task', s.task));
    title.appendChild(toned(el('span', 'chip-state', s.state), s.state));
    title.appendChild(el('span', 'step-attempts',
      s.attempts.length === 1 ? '1 attempt' : s.attempts.length + ' attempts'));
    body.appendChild(title);

    var ids = el('div', 'step-ids');
    ids.appendChild(el('span', 'anywhere',
      'queue_seq ' + s.pos + ' · handoff_key ' + (s.handoffKey || '—')));
    ids.appendChild(el('span', 'anywhere',
      'enqueued by ' + (s.parent || 'intake, no parent run') + ' · chain_depth ' + s.depth));
    if (s.inputFrom) {
      ids.appendChild(el('span', 'anywhere', 'read output of ' + s.inputFrom));
    }
    body.appendChild(ids);

    /* A cancelled entry is planned-then-dropped work. Saying so is the
       interesting part of a revised route — the only place the ledger shows a
       plan changing rather than progressing. */
    if (s.state === 'CANCELLED') {
      body.appendChild(el('div', 'step-note', 'cancelled before it ran'));
    }

    s.attempts.forEach(function (run) { body.appendChild(attemptNode(ticket, run)); });
    wrap.appendChild(body);
    return wrap;
  }

  function attemptNode(ticket, run) {
    var node = el('div', 'attempt');
    var line = toned(el('div', 'attempt-line'), run.state);
    line.appendChild(el('span', 'chip', 'attempt ' + (run.attempt === undefined ? '?' : run.attempt)));
    line.appendChild(el('span', 'state', run.state));
    line.appendChild(el('span', 'dim', shortRun(run.run_id)));
    line.appendChild(el('span', 'dim', metered(run) ? money(run.cost_usd) : 'cost_usd unmetered'));
    // `attempt_started_at` is the only timestamp a run carries — there is no
    // completion time in the record, so this is when it STARTED, not when it
    // finished, and it says so.
    if (run.attempt_started_at) line.appendChild(stamped('dim', 'started ', run.attempt_started_at));
    node.appendChild(line);

    var artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
    if (artifacts.length) {
      var list = el('div', 'artifacts');
      artifacts.forEach(function (path) {
        var href = artifactUrl(ticket.ticket_id, run.run_id, path);
        if (!href) {
          // Unlinkable path (scheme, traversal, or hostile string) — shown as
          // text so it is still visible, never as a live href.
          list.appendChild(el('span', 'artifact-plain', path));
          return;
        }
        var kind = artifactKind(path);
        var a = el('a', kind === 'opaque' ? null : 'artifact-link', path);
        if (kind === 'opaque') {
          a.href = href;
          a.rel = 'noopener';
        } else {
          a.href = artifactHref(ticket.ticket_id, run.run_id, path);
        }
        list.appendChild(a);
      });
      node.appendChild(list);
    }

    if (run.detail) node.appendChild(el('span', 'attempt-note', run.detail));
    return node;
  }

  /* ---- shell ------------------------------------------------------------- */

  var current = null;
  var MAIN_SECTIONS = ['sec-attention', 'sec-gates', 'sec-board', 'sec-spend'];

  function params() {
    var q = new URLSearchParams(location.search);
    return { ticket: q.get('ticket'), run: q.get('run'), artifact: q.get('artifact') };
  }

  function render() {
    if (!current) return;
    var p = params();
    renderAttention(current);
    renderGates(current);
    renderBoard(current, p.ticket);
    renderSpend(current);
    renderHealth(current);
    renderDetail(current, p.ticket);
    renderArtifact(p);
  }

  function navigate(url) {
    history.pushState({}, '', url);
    render();
    window.scrollTo({ top: 0 });
  }

  function ticketHref(ticketId) {
    return ticketId === null ? location.pathname
      : location.pathname + '?ticket=' + encodeURIComponent(ticketId);
  }

  function artifactHref(ticketId, runId, path) {
    return location.pathname + '?ticket=' + encodeURIComponent(ticketId) +
      '&run=' + encodeURIComponent(runId) + '&artifact=' + encodeURIComponent(path);
  }

  function select(ticketId) {
    navigate(ticketHref(ticketId));
    document.getElementById('detail-pane').scrollIntoView({ block: 'nearest' });
  }

  /* ---- artifact viewer --------------------------------------------------- */

  /* Resolver handed to the markdown renderer. Artifact content is the least
     trusted data on the page, so this is the only thing standing between a
     `[click](javascript:...)` in a spec and a live link: anything that isn't
     http(s) or a containable relative path returns null, and the renderer
     prints it as text instead. */
  function artifactResolver(ticketId, runId, path) {
    var base = artifactBase(ticketId, runId);
    var dir = path.indexOf('/') === -1 ? '' : path.slice(0, path.lastIndexOf('/') + 1);
    return function (href) {
      if (typeof href !== 'string' || !href) return null;
      if (/^https?:\/\//i.test(href)) return href;
      if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(href) || href.charAt(0) === '#') return null;
      if (!base) return null;
      // Artifact paths in the ledger are namespace-relative (`specs/30/x.png`),
      // but markdown inside a file may also link a sibling (`screenshots/x.png`).
      var candidate = href.indexOf('specs/') === 0 ? href : dir + href;
      var segs = safeRelPath(candidate);
      return segs ? base + segs.map(encodeURIComponent).join('/') : null;
    };
  }

  function renderArtifact(p) {
    var host = document.getElementById('artifact-view');
    var showing = !!(p.artifact && p.run && p.ticket);
    host.hidden = !showing;
    // A failed fetch already owns the main column; don't fight it for control
    // of these sections.
    if (document.getElementById('fetch-error').hidden) {
      MAIN_SECTIONS.forEach(function (id) { document.getElementById(id).hidden = showing; });
    }
    if (!showing) return;

    clear(host);
    var url = artifactUrl(p.ticket, p.run, p.artifact);

    var head = el('div', 'section-head');
    var back = el('a', 'btn', '← Back to ticket #' + p.ticket);
    back.href = ticketHref(p.ticket);
    head.appendChild(back);
    head.appendChild(el('h2', 'ds-h3 anywhere', p.artifact));
    if (url) {
      var raw = el('a', 'section-note', 'raw');
      raw.href = url;
      raw.rel = 'noopener';
      head.appendChild(raw);
    }
    head.appendChild(el('span', 'section-note', 'produced by run ' + shortRun(p.run)));
    host.appendChild(head);

    var body = el('div', 'panel artifact-body');
    host.appendChild(body);

    if (!url) {
      body.appendChild(el('p', 'md-p', 'That artifact path cannot be addressed safely, so it is not fetched.'));
      return;
    }

    var kind = artifactKind(p.artifact);
    if (kind === 'image') {
      var img = el('img', 'artifact-image');
      img.src = url;
      img.alt = p.artifact;
      body.appendChild(img);
      return;
    }
    if (kind === 'opaque') {
      body.appendChild(el('p', 'md-p',
        'No inline view for this file type. Use the raw link above to download it.'));
      return;
    }

    body.appendChild(el('p', 'md-p muted', 'Loading…'));
    fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('artifact returned ' + res.status);
        return res.text();
      })
      .then(function (text) {
        clear(body);
        if (kind === 'markdown') {
          var prose = el('div', 'md-prose');
          prose.appendChild(window.AgentHqMarkdown.render(
            text, artifactResolver(p.ticket, p.run, p.artifact)));
          body.appendChild(prose);
        } else {
          body.appendChild(el('pre', 'md-pre')).appendChild(el('code', null, text));
        }
      })
      .catch(function (err) {
        clear(body);
        body.appendChild(el('p', 'md-p', String(err.message || err)));
      });
  }

  function showFetchError(message) {
    ['sec-attention', 'sec-gates', 'sec-board', 'sec-spend'].forEach(function (id) {
      document.getElementById(id).hidden = true;
    });
    document.getElementById('detail-pane').hidden = true;
    var host = document.getElementById('fetch-error');
    host.hidden = false;
    clear(host);
    var card = el('div', 'state-card');
    card.style.setProperty('--tone', 'var(--destructive)');
    card.appendChild(el('span', 'kind', 'FETCH FAILED'));
    card.appendChild(el('span', 'headline', 'The state branch could not be read.'));
    card.appendChild(el('span', 'body', message));
    var retry = el('button', 'btn', 'Retry');
    retry.type = 'button';
    retry.addEventListener('click', function () { load(true); });
    card.appendChild(retry);
    host.appendChild(card);
  }

  function clearFetchError() {
    document.getElementById('fetch-error').hidden = true;
    ['sec-attention', 'sec-gates', 'sec-board', 'sec-spend'].forEach(function (id) {
      document.getElementById(id).hidden = false;
    });
    document.getElementById('detail-pane').hidden = false;
  }

  function load(force) {
    var btn = document.getElementById('refresh');
    btn.setAttribute('aria-busy', 'true');
    // `cache: reload` is the strongest ask available; raw.githubusercontent
    // still serves up to 5 minutes stale, which is why the stamp is shown.
    fetch(DATA_URL, force ? { cache: 'reload' } : {})
      .then(function (res) {
        if (!res.ok) throw new Error('dashboard.json returned ' + res.status + ' on ' + STATE_BRANCH + '.');
        return res.json();
      })
      .then(function (data) {
        clearFetchError();
        current = model(data);
        document.getElementById('generated-at').textContent = data.generated_at || 'unknown';
        document.getElementById('generated-ago').textContent = ago(data.generated_at);
        render();
      })
      .catch(function (err) {
        showFetchError(String(err.message || err) +
          ' If this install is private, the dashboard cannot read state — use the agent-hq CLI instead.');
      })
      .then(function () { btn.removeAttribute('aria-busy'); });
  }

  /* theme: follow the OS, let the toggle override for this browser */
  function applyTheme(theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.getElementById('theme-label').textContent = theme === 'dark' ? 'Dark' : 'Light';
    try { localStorage.setItem('agent-hq:theme', theme); } catch (e) { /* private mode */ }
  }
  function initialTheme() {
    var stored = null;
    try { stored = localStorage.getItem('agent-hq:theme'); } catch (e) { /* private mode */ }
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  /* Any link back into this same page is a view change, not a navigation:
     ticket cards, artifact links and the viewer's back button all route
     here. Links that leave the page (github.com, raw.githubusercontent)
     have a different pathname and are left alone. */
  document.addEventListener('click', function (e) {
    var link = e.target.closest ? e.target.closest('a[href]') : null;
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    var url;
    try { url = new URL(link.href, location.href); } catch (err) { return; }
    if (url.origin !== location.origin || url.pathname !== location.pathname) return;
    e.preventDefault();
    navigate(url.pathname + url.search);
  });
  window.addEventListener('popstate', render);
  document.getElementById('refresh').addEventListener('click', function () { load(true); });
  document.getElementById('theme').addEventListener('click', function () {
    applyTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark');
  });

  applyTheme(initialTheme());
  if (!REPO_RE.test(ENGINE_REPO)) {
    showFetchError('No engine repo configured. Set <meta name="agent-hq:engine-repo"> in index.html to owner/repo.');
  } else {
    load(false);
  }
})();
