const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8085;
const APP_PATH = path.join(__dirname, 'index.html');
const CONFIG_PATH = path.join(__dirname, '..', '..', 'eval', 'evaluation_config.json');

// In-memory state for live simulation triggers
let state = {
  cycles: 164,
  netAccuracy: 90.3,
  scopeDrift: 0.00,
  overnightPassCount: 16,
  model: 'gemma4:e4b',
  shieldVersion: 'V9.1 FORENSIC SHIELD+'
};

// Step diffs payload generator
function getStepDiffData(step) {
  const diffs = {
    1: {
      title: 'Step 1: Key Parity & Boundary Audit',
      lines: [
        { num: '1', text: '# Protocol XML Mutation: Key Parity Enforcement', type: 'cmt' },
        { num: '2', text: '- 1. State Verification: Check database keys manually.', type: 'del' },
        { num: '3', text: '+ 1. Side-by-Side Key Parity: Compare string literals in .get() against DB keys side-by-side.', type: 'add' },
        { num: '4', text: '+ 2. Empirical Alignment Dry-Run: Execute validator script with Live-Shaped Data.', type: 'add' },
        { num: '5', text: '+ 3. Scope Restriction: Restrict all edits strictly within target line bounds.', type: 'add' }
      ]
    },
    2: {
      title: 'Step 2: Red Team Boundary Injection',
      lines: [
        { num: '1', text: '# Protocol XML Mutation: Red Team Division Guard', type: 'cmt' },
        { num: '2', text: '- if budget == 0: return fallback_result', type: 'del' },
        { num: '3', text: '+ if budget <= 0: raise ScopeDriftViolation("Adversarial budget depletion detected")', type: 'add' }
      ]
    },
    3: {
      title: 'Step 3: Forensic Dry-Run Alignment',
      lines: [
        { num: '1', text: '# Protocol XML Mutation: Dry-Run Alignment Validation', type: 'cmt' },
        { num: '2', text: '- run_tests_blindly()', type: 'del' },
        { num: '3', text: '+ execute_forensic_dry_run(shape_validator=True, strict_keys=True)', type: 'add' }
      ]
    },
    4: {
      title: 'Step 4: Tier 8 Assertion Execution',
      lines: [
        { num: '1', text: '# Protocol XML Mutation: Final Tier 8 Verification', type: 'cmt' },
        { num: '2', text: '+ assert forensic_shield.score == 1.0', type: 'add' },
        { num: '3', text: '+ assert scope_drift_violations == 0', type: 'add' }
      ]
    }
  };
  return diffs[step] || diffs[1];
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API Route: Status
  if (url.pathname === '/api/status' && req.method === 'GET') {
    let taskCount = 55;
    try {
      if (fs.existsSync(CONFIG_PATH)) {
        const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
        if (cfg.tiers) {
          taskCount = Object.values(cfg.tiers).reduce((acc, arr) => acc + arr.length, 0);
        }
      }
    } catch (e) {
      console.error('Error reading eval config:', e.message);
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      ok: true,
      data: {
        ...state,
        totalTasks: taskCount,
        timestamp: new Date().toISOString()
      }
    }));
    return;
  }

  // API Route: Diff
  if (url.pathname === '/api/diff' && req.method === 'GET') {
    const step = parseInt(url.searchParams.get('step') || '1', 10);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      ok: true,
      step: step,
      data: getStepDiffData(step)
    }));
    return;
  }

  // API Route: Trigger Simulation / Execution
  if (url.pathname === '/api/simulate' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      state.cycles += 1;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        ok: true,
        message: 'Simulation run recorded',
        newCycles: state.cycles
      }));
    });
    return;
  }

  // Static File Fallback (Index.html for all page routes)
  fs.readFile(APP_PATH, 'utf8', (err, data) => {
    if (err) {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('Error loading prototype HTML: ' + err.message);
    } else {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(data);
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Mighty Mouse Autoresearch Server running at http://localhost:${PORT}`);
});
