#!/usr/bin/env python3
"""
Enhanced Flask Dashboard for Auto Class Joiner Monitoring
Provides real-time logs, screenshots, meeting status, and mobile-responsive control interface
"""

from flask import Flask, render_template, render_template_string, jsonify, send_from_directory, request, Response
import os
import json
import glob
import datetime
from pathlib import Path
import threading
import time

app = Flask(__name__)

# Configuration - Fixed path issues
LOGS_DIR = "/app/logs_pranav"
SCREENSHOTS_DIR = "/app/screenshots_pranav"
LOG_FILE = os.path.join(LOGS_DIR, "class_joiner.log")
STATUS_FILE = os.path.join(LOGS_DIR, "app_status.json")
SCREENSHOT_TRIGGER_FILE = os.path.join(LOGS_DIR, "take_screenshot")

# Ensure directories exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

class LogMonitor:
    def __init__(self):
        self.latest_logs = []
        self.max_logs = 1000  # Increased to show more logs
        self.last_position = 0

    def get_all_logs(self):
        """Get ALL log entries from the file"""
        try:
            if not os.path.exists(LOG_FILE):
                return []

            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines if line.strip()]
        except Exception as e:
            return [f"Error reading logs: {str(e)}"]

    def get_latest_logs(self, lines=100):
        """Get the latest log entries"""
        try:
            if not os.path.exists(LOG_FILE):
                return []

            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:] if line.strip()]
        except Exception as e:
            return [f"Error reading logs: {str(e)}"]

    def get_new_logs_since_position(self):
        """Get new log entries since last check"""
        try:
            if not os.path.exists(LOG_FILE):
                return [], 0

            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_content = f.read()
                self.last_position = f.tell()

                if new_content:
                    new_lines = [line.strip() for line in new_content.split('\n') if line.strip()]
                    return new_lines, self.last_position

        except Exception as e:
            return [f"Error reading new logs: {str(e)}"], self.last_position

        return [], self.last_position

log_monitor = LogMonitor()

def get_app_status():
    """Get current application status"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading status file: {e}")
    
    # Default status if file doesn't exist or can't be read
    return {
        "status": "Unknown",
        "timestamp": datetime.datetime.now().isoformat(),
        "meeting_info": {}
    }

def get_screenshots():
    """Get list of available screenshots"""
    screenshot_patterns = [
        os.path.join(SCREENSHOTS_DIR, "screenshot_*.png"),
        os.path.join(LOGS_DIR, "screenshot_*.png"),
        os.path.join(LOGS_DIR, "screenshots", "screenshot_*.png")
    ]

    screenshots = []
    for pattern in screenshot_patterns:
        screenshots.extend(glob.glob(pattern))

    # Sort by modification time (newest first)
    screenshots.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    screenshot_data = []
    for screenshot in screenshots[:20]:  # Increased to 20 most recent
        try:
            stat = os.stat(screenshot)
            screenshot_data.append({
                'filename': os.path.basename(screenshot),
                'path': screenshot,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'modified_timestamp': stat.st_mtime
            })
        except Exception as e:
            print(f"Error processing screenshot {screenshot}: {e}")

    return screenshot_data

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template_string(ENHANCED_DASHBOARD_HTML)

@app.route('/api/logs')
def get_logs():
    """API endpoint to get logs"""
    lines = request.args.get('lines', 100, type=int)
    get_all = request.args.get('all', 'false').lower() == 'true'
    
    if get_all:
        logs = log_monitor.get_all_logs()
    else:
        logs = log_monitor.get_latest_logs(lines)
    
    return jsonify({'logs': logs, 'total': len(logs)})

@app.route('/api/logs/stream')
def stream_logs():
    """Server-sent events for real-time log streaming"""
    def generate():
        while True:
            new_logs, _ = log_monitor.get_new_logs_since_position()
            if new_logs:
                for log_line in new_logs:
                    yield f"data: {json.dumps({'log': log_line, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            time.sleep(1)

    return Response(generate(), mimetype='text/plain')

@app.route('/api/status')
def get_status():
    """Get comprehensive application status"""
    try:
        app_status_data = get_app_status()
        
        # Check if log file exists and get last modified time
        log_exists = os.path.exists(LOG_FILE)
        last_log_time = None
        if log_exists:
            last_log_time = datetime.datetime.fromtimestamp(os.path.getmtime(LOG_FILE)).isoformat()

        # Check if main application is running (based on recent log activity)
        app_running = False
        if log_exists:
            current_time = time.time()
            log_modified_time = os.path.getmtime(LOG_FILE)
            app_running = (current_time - log_modified_time) < 300  # 5 minutes

        # Get recent screenshots count
        screenshots = get_screenshots()
        recent_screenshots = len([s for s in screenshots if time.time() - s['modified_timestamp'] < 3600])  # Last hour

        return jsonify({
            'app_running': app_running,
            'log_file_exists': log_exists,
            'last_log_time': last_log_time,
            'recent_screenshots': recent_screenshots,
            'total_screenshots': len(screenshots),
            'app_status': app_status_data['status'],
            'meeting_info': app_status_data.get('meeting_info', {}),
            'status_timestamp': app_status_data.get('timestamp')
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/screenshots')
def get_screenshots_api():
    """API endpoint to get available screenshots"""
    screenshots = get_screenshots()
    return jsonify({'screenshots': screenshots})

@app.route('/api/screenshot/trigger')
def trigger_screenshot():
    """API endpoint to trigger a screenshot"""
    try:
        # Create the trigger file
        with open(SCREENSHOT_TRIGGER_FILE, 'w') as f:
            f.write(f"Screenshot requested at {datetime.datetime.now()}")
        return jsonify({'success': True, 'message': 'Screenshot triggered successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error triggering screenshot: {str(e)}'})

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    """Serve screenshot files"""
    # Try different possible directories
    possible_dirs = [
        SCREENSHOTS_DIR,
        os.path.join(LOGS_DIR, "screenshots"),
        LOGS_DIR,
        "/tmp/screenshots",
        "/tmp"
    ]

    for directory in possible_dirs:
        filepath = os.path.join(directory, filename)
        if os.path.exists(filepath):
            return send_from_directory(directory, filename)

    return "Screenshot not found", 404

# Enhanced HTML Template with Mobile Responsiveness and Meeting Info
ENHANCED_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auto Class Joiner Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 10px;
        }

        .dashboard {
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #2c3e50, #3498db);
            color: white;
            padding: 20px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .status-bar {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 20px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
        }

        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #e74c3c;
        }

        .status-indicator.active {
            background: #2ecc71;
            animation: pulse 2s infinite;
        }

        .status-indicator.warning {
            background: #f39c12;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        /* Meeting Status Panel */
        .meeting-status {
            background: linear-gradient(135deg, #8e44ad, #9b59b6);
            color: white;
            padding: 20px;
            margin: 20px;
            border-radius: 10px;
            display: none;
        }

        .meeting-status.active {
            display: block;
        }

        .meeting-title {
            font-size: 1.5em;
            margin-bottom: 10px;
        }

        .meeting-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .meeting-detail {
            background: rgba(255, 255, 255, 0.1);
            padding: 10px;
            border-radius: 5px;
        }

        .meeting-detail-label {
            font-weight: bold;
            margin-bottom: 5px;
        }

        .main-content {
            padding: 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            min-height: 600px;
        }

        .panel {
            background: white;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .panel-header {
            background: #f8f9fa;
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .panel-header h3 {
            color: #2c3e50;
            font-size: 1.3em;
        }

        .panel-controls {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        .btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
            transition: background 0.3s;
            white-space: nowrap;
        }

        .btn:hover {
            background: #2980b9;
        }

        .btn:disabled {
            background: #95a5a6;
            cursor: not-allowed;
        }

        .btn.success {
            background: #27ae60;
        }

        .btn.success:hover {
            background: #229954;
        }

        .btn.small {
            padding: 6px 12px;
            font-size: 11px;
        }

        .logs-container {
            height: 500px;
            overflow-y: auto;
            background: #1e1e1e;
            color: #f8f8f2;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            padding: 15px;
            flex-grow: 1;
        }

        .log-line {
            margin-bottom: 3px;
            padding: 2px 0;
            word-wrap: break-word;
            line-height: 1.4;
        }

        .log-line.info {
            color: #8be9fd;
        }

        .log-line.error {
            color: #ff5555;
            background: rgba(255, 85, 85, 0.1);
            padding: 3px;
            border-radius: 3px;
        }

        .log-line.warning {
            color: #ffb86c;
            background: rgba(255, 184, 108, 0.1);
            padding: 3px;
            border-radius: 3px;
        }

        .screenshots-grid {
            padding: 15px;
            max-height: 500px;
            overflow-y: auto;
            flex-grow: 1;
        }

        .screenshot-item {
            display: flex;
            align-items: center;
            padding: 10px;
            border-bottom: 1px solid #e9ecef;
            transition: background 0.3s;
        }

        .screenshot-item:hover {
            background: #f8f9fa;
        }

        .screenshot-thumb {
            width: 80px;
            height: 60px;
            object-fit: cover;
            border-radius: 5px;
            margin-right: 15px;
            cursor: pointer;
        }

        .screenshot-info {
            flex-grow: 1;
            min-width: 0;
        }

        .screenshot-filename {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
            word-break: break-all;
        }

        .screenshot-meta {
            color: #7f8c8d;
            font-size: 11px;
        }

        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .auto-refresh input[type="checkbox"] {
            transform: scale(1.2);
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }

        .controls {
            background: #f8f9fa;
            padding: 15px;
            border-top: 1px solid #e9ecef;
            display: flex;
            gap: 10px;
            justify-content: center;
            flex-wrap: wrap;
        }

        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            background: #27ae60;
            color: white;
            border-radius: 5px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
            max-width: calc(100vw - 40px);
        }

        .notification.show {
            opacity: 1;
            transform: translateX(0);
        }

        .notification.error {
            background: #e74c3c;
        }

        .log-stats {
            background: #f8f9fa;
            padding: 10px 15px;
            border-bottom: 1px solid #e9ecef;
            font-size: 12px;
            color: #7f8c8d;
        }

        /* Mobile Responsive Styles */
        @media (max-width: 768px) {
            body {
                padding: 5px;
            }

            .header h1 {
                font-size: 1.8em;
            }

            .status-bar {
                flex-direction: column;
                gap: 10px;
            }

            .status-item {
                justify-content: center;
            }

            .main-content {
                grid-template-columns: 1fr;
                gap: 15px;
                padding: 15px;
            }

            .panel-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }

            .panel-controls {
                width: 100%;
                justify-content: space-between;
            }

            .logs-container {
                height: 400px;
                font-size: 11px;
                padding: 10px;
            }

            .screenshots-grid {
                height: 400px;
                padding: 10px;
            }

            .screenshot-item {
                flex-direction: column;
                align-items: flex-start;
            }

            .screenshot-thumb {
                width: 100%;
                height: 120px;
                margin-right: 0;
                margin-bottom: 10px;
            }

            .controls {
                flex-direction: column;
                gap: 10px;
            }

            .meeting-details {
                grid-template-columns: 1fr;
            }

            .notification {
                right: 10px;
                left: 10px;
                max-width: none;
            }
        }

        @media (max-width: 480px) {
            .header h1 {
                font-size: 1.5em;
            }

            .logs-container {
                height: 300px;
                font-size: 10px;
            }

            .screenshots-grid {
                height: 300px;
            }

            .btn {
                padding: 6px 12px;
                font-size: 11px;
            }
        }

        /* Dark mode for logs */
        @media (prefers-color-scheme: dark) {
            .logs-container {
                background: #0d1117;
                color: #c9d1d9;
            }

            .log-line.info {
                color: #79c0ff;
            }

            .log-line.error {
                color: #f85149;
                background: rgba(248, 81, 73, 0.1);
            }

            .log-line.warning {
                color: #d29922;
                background: rgba(210, 153, 34, 0.1);
            }
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>Auto Class Joiner Dashboard</h1>
            <div class="status-bar">
                <div class="status-item">
                    <div class="status-indicator" id="app-status"></div>
                    <span id="app-status-text">Checking...</span>
                </div>
                <div class="status-item">
                    <div class="status-indicator" id="log-status"></div>
                    <span id="log-status-text">Logs: Unknown</span>
                </div>
                <div class="status-item">
                    <div class="status-indicator" id="screenshot-status"></div>
                    <span id="screenshot-status-text">Screenshots: Unknown</span>
                </div>
            </div>
        </div>

        <!-- Meeting Status Panel -->
        <div class="meeting-status" id="meeting-status">
            <div class="meeting-title" id="meeting-title">Meeting in Progress</div>
            <div class="meeting-details">
                <div class="meeting-detail">
                    <div class="meeting-detail-label">Status</div>
                    <div id="meeting-status-text">Unknown</div>
                </div>
                <div class="meeting-detail">
                    <div class="meeting-detail-label">Meeting ID</div>
                    <div id="meeting-id">-</div>
                </div>
                <div class="meeting-detail">
                    <div class="meeting-detail-label">Instructor</div>
                    <div id="meeting-instructor">-</div>
                </div>
                <div class="meeting-detail">
                    <div class="meeting-detail-label">Connection Time</div>
                    <div id="connection-time">-</div>
                </div>
            </div>
        </div>

        <div class="main-content">
            <div class="panel">
                <div class="panel-header">
                    <h3>Real-time Logs</h3>
                    <div class="panel-controls">
                        <div class="auto-refresh">
                            <input type="checkbox" id="auto-scroll" checked>
                            <label for="auto-scroll">Auto-scroll</label>
                        </div>
                        <button class="btn small" id="show-all-logs">Show All</button>
                    </div>
                </div>
                <div class="log-stats" id="log-stats">
                    Loading log information...
                </div>
                <div class="logs-container" id="logs-container">
                    <div class="loading">Loading logs...</div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <h3>Screenshots</h3>
                    <div class="panel-controls">
                        <button class="btn success" id="take-screenshot">Take Screenshot</button>
                        <button class="btn small" id="refresh-screenshots-btn">Refresh</button>
                    </div>
                </div>
                <div class="screenshots-grid" id="screenshots-container">
                    <div class="loading">Loading screenshots...</div>
                </div>
            </div>
        </div>

        <div class="controls">
            <button class="btn" id="refresh-logs">Refresh Logs</button>
            <button class="btn" id="clear-logs">Clear Display</button>
            <button class="btn" id="refresh-all">Refresh All</button>
        </div>
    </div>

    <div class="notification" id="notification"></div>

    <script>
        class EnhancedDashboard {
            constructor() {
                this.autoScroll = true;
                this.showingAllLogs = false;
                this.eventSource = null;
                this.init();
            }

            init() {
                this.bindEvents();
                this.loadInitialData();
                this.startRealTimeUpdates();
                this.updateStatus();

                // Update status every 15 seconds for more responsive meeting info
                setInterval(() => this.updateStatus(), 15000);
                // Refresh screenshots every 60 seconds
                setInterval(() => this.loadScreenshots(), 60000);
            }

            bindEvents() {
                document.getElementById('take-screenshot').addEventListener('click', () => this.takeScreenshot());
                document.getElementById('refresh-logs').addEventListener('click', () => this.loadLogs());
                document.getElementById('refresh-screenshots-btn').addEventListener('click', () => this.loadScreenshots());
                document.getElementById('clear-logs').addEventListener('click', () => this.clearLogs());
                document.getElementById('refresh-all').addEventListener('click', () => this.refreshAll());
                document.getElementById('show-all-logs').addEventListener('click', () => this.toggleAllLogs());
                document.getElementById('auto-scroll').addEventListener('change', (e) => {
                    this.autoScroll = e.target.checked;
                });
            }

            async loadInitialData() {
                await Promise.all([
                    this.loadLogs(),
                    this.loadScreenshots()
                ]);
            }

            async loadLogs() {
                try {
                    const url = this.showingAllLogs ? '/api/logs?all=true' : '/api/logs?lines=200';
                    const response = await fetch(url);
                    const data = await response.json();
                    this.displayLogs(data.logs, false);
                    this.updateLogStats(data.total, data.logs.length);
                } catch (error) {
                    console.error('Error loading logs:', error);
                    this.showNotification('Error loading logs', 'error');
                }
            }

            async toggleAllLogs() {
                const button = document.getElementById('show-all-logs');
                this.showingAllLogs = !this.showingAllLogs;
                
                if (this.showingAllLogs) {
                    button.textContent = 'Show Recent';
                    button.disabled = true;
                    this.showNotification('Loading all logs...');
                    await this.loadLogs();
                    button.disabled = false;
                } else {
                    button.textContent = 'Show All';
                    await this.loadLogs();
                }
            }

            updateLogStats(total, showing) {
                const statsElement = document.getElementById('log-stats');
                const status = this.showingAllLogs ? `Showing all ${total} logs` : `Showing ${showing} of ${total} logs`;
                statsElement.textContent = status;
            }

            async loadScreenshots() {
                try {
                    const response = await fetch('/api/screenshots');
                    const data = await response.json();
                    this.displayScreenshots(data.screenshots);
                } catch (error) {
                    console.error('Error loading screenshots:', error);
                    this.showNotification('Error loading screenshots', 'error');
                }
            }

            async refreshAll() {
                const button = document.getElementById('refresh-all');
                const originalText = button.textContent;
                button.disabled = true;
                button.textContent = 'Refreshing...';

                try {
                    await Promise.all([
                        this.loadLogs(),
                        this.loadScreenshots(),
                        this.updateStatus()
                    ]);
                    this.showNotification('Dashboard refreshed successfully!');
                } catch (error) {
                    this.showNotification('Error refreshing dashboard', 'error');
                } finally {
                    button.disabled = false;
                    button.textContent = originalText;
                }
            }

            async updateStatus() {
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();

                    // Update app status
                    const appStatus = document.getElementById('app-status');
                    const appStatusText = document.getElementById('app-status-text');
                    if (data.app_running) {
                        appStatus.classList.add('active');
                        appStatus.classList.remove('warning');
                        appStatusText.textContent = `App: ${data.app_status || 'Running'}`;
                    } else {
                        appStatus.classList.remove('active');
                        appStatus.classList.add('warning');
                        appStatusText.textContent = 'App: Stopped';
                    }

                    // Update log status
                    const logStatus = document.getElementById('log-status');
                    const logStatusText = document.getElementById('log-status-text');
                    if (data.log_file_exists) {
                        logStatus.classList.add('active');
                        logStatusText.textContent = 'Logs: Active';
                    } else {
                        logStatus.classList.remove('active');
                        logStatusText.textContent = 'Logs: No file';
                    }

                    // Update screenshot status
                    const screenshotStatus = document.getElementById('screenshot-status');
                    const screenshotStatusText = document.getElementById('screenshot-status-text');
                    if (data.total_screenshots > 0) {
                        screenshotStatus.classList.add('active');
                        screenshotStatusText.textContent = `Screenshots: ${data.total_screenshots} total, ${data.recent_screenshots} recent`;
                    } else {
                        screenshotStatus.classList.remove('active');
                        screenshotStatusText.textContent = 'Screenshots: None';
                    }

                    // Update meeting information
                    this.updateMeetingStatus(data.meeting_info, data.app_status);
                    
                } catch (error) {
                    console.error('Error updating status:', error);
                }
            }

            updateMeetingStatus(meetingInfo, appStatus) {
                const meetingPanel = document.getElementById('meeting-status');
                const meetingTitle = document.getElementById('meeting-title');
                const meetingStatusText = document.getElementById('meeting-status-text');
                const meetingId = document.getElementById('meeting-id');
                const meetingInstructor = document.getElementById('meeting-instructor');
                const connectionTime = document.getElementById('connection-time');

                // Check if there's active meeting info
                if (meetingInfo && Object.keys(meetingInfo).length > 0) {
                    meetingPanel.classList.add('active');
                    
                    // Update meeting details
                    if (meetingInfo.title) {
                        meetingTitle.textContent = meetingInfo.title;
                    } else {
                        meetingTitle.textContent = 'Active Meeting';
                    }

                    meetingStatusText.textContent = this.formatMeetingStatus(meetingInfo.status, appStatus);
                    meetingId.textContent = meetingInfo.id || '-';
                    meetingInstructor.textContent = meetingInfo.instructor || '-';
                    
                    // Show connection time remaining if available
                    if (meetingInfo.connection_remaining) {
                        const minutes = Math.floor(meetingInfo.connection_remaining / 60);
                        const seconds = meetingInfo.connection_remaining % 60;
                        connectionTime.textContent = `${minutes}:${seconds.toString().padStart(2, '0')} remaining`;
                    } else if (meetingInfo.status === 'connected') {
                        connectionTime.textContent = 'Connected';
                    } else {
                        connectionTime.textContent = '-';
                    }
                } else {
                    // Check if we should show the panel based on app status
                    if (appStatus && (appStatus.includes('meeting') || appStatus.includes('Meeting') || appStatus.includes('Connecting'))) {
                        meetingPanel.classList.add('active');
                        meetingTitle.textContent = 'Class Session Activity';
                        meetingStatusText.textContent = appStatus;
                        meetingId.textContent = '-';
                        meetingInstructor.textContent = '-';
                        connectionTime.textContent = '-';
                    } else {
                        meetingPanel.classList.remove('active');
                    }
                }
            }

            formatMeetingStatus(status, appStatus) {
                const statusMap = {
                    'found': 'Meeting Detected',
                    'connecting': 'Connecting to Meeting',
                    'connected': 'Connected to Meeting',
                    'fetch_failed': 'Failed to Fetch Meeting Details',
                    'url_failed': 'Failed to Extract Session URL',
                    'token_failed': 'Failed to Get Session Token',
                    'error': 'Connection Error'
                };
                
                return statusMap[status] || appStatus || 'Unknown Status';
            }

            startRealTimeUpdates() {
                // Use polling for better compatibility
                this.startPolling();
            }

            startPolling() {
                // Poll for new logs every 3 seconds
                setInterval(async () => {
                    if (!this.showingAllLogs) { // Only poll when showing recent logs
                        try {
                            const response = await fetch('/api/logs?lines=10');
                            const data = await response.json();
                            if (data.logs.length > 0) {
                                const container = document.getElementById('logs-container');
                                const lastLog = container.lastElementChild?.textContent;
                                const newLog = data.logs[data.logs.length - 1];
                                if (lastLog !== newLog) {
                                    this.appendLog(newLog);
                                }
                            }
                        } catch (error) {
                            console.error('Polling error:', error);
                        }
                    }
                }, 3000);
            }

            displayLogs(logs, append = false) {
                const container = document.getElementById('logs-container');
                if (!append) {
                    container.innerHTML = '';
                }

                logs.forEach(log => {
                    this.appendLog(log, false);
                });

                if (this.autoScroll) {
                    container.scrollTop = container.scrollHeight;
                }
            }

            appendLog(logText, scroll = true) {
                const container = document.getElementById('logs-container');
                const logElement = document.createElement('div');
                logElement.className = 'log-line';

                // Add appropriate class based on log level
                if (logText.includes('ERROR')) {
                    logElement.classList.add('error');
                } else if (logText.includes('WARNING') || logText.includes('WARN')) {
                    logElement.classList.add('warning');
                } else if (logText.includes('INFO')) {
                    logElement.classList.add('info');
                }

                logElement.textContent = logText;
                container.appendChild(logElement);

                // Keep only last 1000 log lines to prevent memory issues
                while (container.children.length > 1000) {
                    container.removeChild(container.firstChild);
                }

                if (this.autoScroll && scroll) {
                    container.scrollTop = container.scrollHeight;
                }
            }

            displayScreenshots(screenshots) {
                const container = document.getElementById('screenshots-container');

                if (screenshots.length === 0) {
                    container.innerHTML = '<div class="loading">No screenshots available</div>';
                    return;
                }

                container.innerHTML = '';
                screenshots.forEach(screenshot => {
                    const item = document.createElement('div');
                    item.className = 'screenshot-item';

                    // Determine screenshot type for better display
                    const isAutoScreenshot = screenshot.filename.includes('15min_auto');
                    const typeLabel = isAutoScreenshot ? ' (Auto 15min)' : '';

                    item.innerHTML = `
                        <img src="/screenshots/${screenshot.filename}" alt="Screenshot" class="screenshot-thumb" 
                             onclick="window.open('/screenshots/${screenshot.filename}', '_blank')" 
                             loading="lazy">
                        <div class="screenshot-info">
                            <div class="screenshot-filename">${screenshot.filename}${typeLabel}</div>
                            <div class="screenshot-meta">
                                ${screenshot.modified} | ${this.formatFileSize(screenshot.size)}
                            </div>
                        </div>
                    `;

                    container.appendChild(item);
                });
            }

            async takeScreenshot() {
                const button = document.getElementById('take-screenshot');
                const originalText = button.textContent;
                button.disabled = true;
                button.textContent = 'Taking...';

                try {
                    const response = await fetch('/api/screenshot/trigger');
                    const data = await response.json();

                    if (data.success) {
                        this.showNotification('Screenshot triggered successfully!');
                        // Refresh screenshots after a delay
                        setTimeout(() => this.loadScreenshots(), 5000);
                    } else {
                        this.showNotification(data.message || 'Failed to trigger screenshot', 'error');
                    }
                } catch (error) {
                    this.showNotification('Error triggering screenshot', 'error');
                } finally {
                    button.disabled = false;
                    button.textContent = originalText;
                }
            }

            clearLogs() {
                document.getElementById('logs-container').innerHTML = '';
                document.getElementById('log-stats').textContent = 'Display cleared';
            }

            formatFileSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }

            showNotification(message, type = 'success') {
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.className = `notification ${type} show`;

                setTimeout(() => {
                    notification.classList.remove('show');
                }, 4000);
            }
        }

        // Initialize dashboard when DOM is loaded
        document.addEventListener('DOMContentLoaded', () => {
            new EnhancedDashboard();
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("Enhanced Flask Dashboard starting...")
    print("Dashboard will be available at:")
    print("- http://localhost:5000 (main dashboard)")
    print("\nNew Features:")
    print("- Mobile responsive design")
    print("- Real-time meeting status display")
    print("- All logs visibility option")
    print("- Enhanced screenshot monitoring (15-min auto screenshots labeled)")
    print("- Improved status monitoring")
    print("- Better error handling and notifications")
    print("- Connection time remaining display")

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)