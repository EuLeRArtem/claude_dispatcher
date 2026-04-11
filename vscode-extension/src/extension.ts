import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

interface TerminalRequest {
	cwd: string;
	command: string;
	title: string;
	timestamp: number;
}

interface KillRequest {
	title: string;
	timestamp: number;
}

const TRIGGER_DIR = path.join(os.homedir(), '.claude-dispatcher');
const TRIGGER_FILE = path.join(TRIGGER_DIR, 'terminal.json');
const KILL_FILE = path.join(TRIGGER_DIR, 'terminal-kill.json');
const ACK_FILE = path.join(TRIGGER_DIR, 'terminal.ack');

let lastTimestamp = 0;
let lastKillTimestamp = 0;

// Track terminals we created so we can dispose them
const managedTerminals = new Map<string, vscode.Terminal>();

export function activate(context: vscode.ExtensionContext) {
	// Ensure trigger directory exists
	if (!fs.existsSync(TRIGGER_DIR)) {
		fs.mkdirSync(TRIGGER_DIR, { recursive: true });
	}

	// Watch for trigger file changes
	const watcher = fs.watch(TRIGGER_DIR, (eventType, filename) => {
		if (filename === 'terminal.json') {
			handleTrigger();
		} else if (filename === 'terminal-kill.json') {
			handleKill();
		}
	});

	// Clean up managed terminals map when terminals close
	const closeListener = vscode.window.onDidCloseTerminal((terminal) => {
		for (const [title, t] of managedTerminals) {
			if (t === terminal) {
				managedTerminals.delete(title);
				break;
			}
		}
	});

	context.subscriptions.push(
		{ dispose: () => watcher.close() },
		closeListener,
	);

	// Check on activation in case file was written before extension started
	if (fs.existsSync(TRIGGER_FILE)) {
		handleTrigger();
	}

	console.log('Claude Dispatcher Terminal extension activated');
}

function handleTrigger(): void {
	try {
		const content = fs.readFileSync(TRIGGER_FILE, 'utf-8');
		const request: TerminalRequest = JSON.parse(content);

		if (request.timestamp <= lastTimestamp) {
			return;
		}
		lastTimestamp = request.timestamp;

		if (!request.command || !request.cwd) {
			console.warn('Claude Dispatcher: invalid trigger — missing command or cwd');
			return;
		}

		const title = request.title || 'Claude Session';

		// Close existing terminal with same title if any
		const existing = managedTerminals.get(title);
		if (existing) {
			existing.dispose();
			managedTerminals.delete(title);
		}

		// Create integrated terminal
		const terminal = vscode.window.createTerminal({
			name: title,
			cwd: request.cwd,
		});

		terminal.show();
		terminal.sendText(request.command);

		// Track it
		managedTerminals.set(title, terminal);

		// Write ack
		fs.writeFileSync(ACK_FILE, String(request.timestamp));

	} catch (err) {
		console.error('Claude Dispatcher: error handling trigger', err);
	}
}

function handleKill(): void {
	try {
		const content = fs.readFileSync(KILL_FILE, 'utf-8');
		const request: KillRequest = JSON.parse(content);

		if (request.timestamp <= lastKillTimestamp) {
			return;
		}
		lastKillTimestamp = request.timestamp;

		const terminal = managedTerminals.get(request.title);
		if (terminal) {
			terminal.dispose();
			managedTerminals.delete(request.title);
		}

		// Write kill ack
		const killAckFile = path.join(TRIGGER_DIR, 'terminal-kill.ack');
		fs.writeFileSync(killAckFile, String(request.timestamp));

	} catch (err) {
		console.error('Claude Dispatcher: error handling kill', err);
	}
}

export function deactivate() {}
