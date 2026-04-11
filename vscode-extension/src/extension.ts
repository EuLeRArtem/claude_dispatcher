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

const TRIGGER_DIR = path.join(os.homedir(), '.claude-dispatcher');
const TRIGGER_FILE = path.join(TRIGGER_DIR, 'terminal.json');

let lastTimestamp = 0;

export function activate(context: vscode.ExtensionContext) {
	// Ensure trigger directory exists
	if (!fs.existsSync(TRIGGER_DIR)) {
		fs.mkdirSync(TRIGGER_DIR, { recursive: true });
	}

	// Watch for trigger file changes
	const watcher = fs.watch(TRIGGER_DIR, (eventType, filename) => {
		if (filename === 'terminal.json') {
			handleTrigger();
		}
	});

	context.subscriptions.push({ dispose: () => watcher.close() });

	// Also check on activation in case file was written before extension started
	if (fs.existsSync(TRIGGER_FILE)) {
		handleTrigger();
	}

	console.log('Claude Dispatcher Terminal extension activated');
}

function handleTrigger(): void {
	try {
		const content = fs.readFileSync(TRIGGER_FILE, 'utf-8');
		const request: TerminalRequest = JSON.parse(content);

		// Deduplication — skip if already processed
		if (request.timestamp <= lastTimestamp) {
			return;
		}
		lastTimestamp = request.timestamp;

		// Validate fields
		if (!request.command || !request.cwd) {
			console.warn('Claude Dispatcher: invalid trigger file — missing command or cwd');
			return;
		}

		// Create integrated terminal
		const terminal = vscode.window.createTerminal({
			name: request.title || 'Claude Session',
			cwd: request.cwd,
		});

		terminal.show();
		terminal.sendText(request.command);

		// Write ack so bot knows it was picked up
		const ackFile = path.join(TRIGGER_DIR, 'terminal.ack');
		fs.writeFileSync(ackFile, String(request.timestamp));

	} catch (err) {
		console.error('Claude Dispatcher: error handling trigger', err);
	}
}

export function deactivate() {}
