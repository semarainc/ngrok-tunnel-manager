from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import json
import threading
import time
import datetime
import os
import logging
from pyngrok import ngrok, conf
import uuid
import traceback
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Database setup
def init_db():
    conn = sqlite3.connect('ngrok_manager.db')
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        api_key TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tunnels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_name TEXT NOT NULL UNIQUE,
        api_key_name TEXT NOT NULL,
        local_addr TEXT NOT NULL,
        tunnel_type TEXT NOT NULL,
        time_limit INTEGER NOT NULL,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        status TEXT DEFAULT 'stopped',
        public_url TEXT DEFAULT '',
        tunnel_id TEXT DEFAULT '',
        log_file TEXT DEFAULT '',
        FOREIGN KEY (api_key_name) REFERENCES api_keys (name)
    )
    ''')

    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# Active tunnel processes
active_tunnels = {}
tunnel_timers = {}

# Helper functions
def get_db_connection():
    conn = sqlite3.connect('ngrok_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

def start_tunnel(app_name):
    conn = get_db_connection()
    tunnel_data = conn.execute('SELECT * FROM tunnels WHERE app_name = ?', (app_name,)).fetchone()
    api_key_data = conn.execute('SELECT api_key FROM api_keys WHERE name = ?', (tunnel_data['api_key_name'],)).fetchone()
    conn.close()

    if not api_key_data:
        return False, "API key not found"

    api_key = api_key_data['api_key']
    local_addr = tunnel_data['local_addr']
    tunnel_type = tunnel_data['tunnel_type']
    time_limit = tunnel_data['time_limit']

    try:
        log_file = tunnel_data['log_file']
        if os.path.exists(log_file):
            os.remove(log_file)
    except:
        pass

    # Create log file for this tunnel
    log_file = f"logs/{str(uuid.uuid4())}.log"

    # Configure ngrok with this API key
    conf.get_default().auth_token = api_key

    # Start the tunnel
    try:
        # Set up a file handler for this tunnel
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Starting tunnel for {app_name} with {tunnel_type} to {local_addr}")

        if tunnel_type == 'http':
            tunnel = ngrok.connect(local_addr, 'http')
            logger.info(f"Created HTTP tunnel: {tunnel.public_url}")
        elif tunnel_type == 'https':
            tunnel = ngrok.connect(local_addr, 'http')  # ngrok handles the https upgrade
            logger.info(f"Created HTTPS tunnel: {tunnel.public_url}")
        elif tunnel_type == 'tcp':
            tunnel = ngrok.connect(local_addr, 'tcp')
            logger.info(f"Created TCP tunnel: {tunnel.public_url}")
        else:
            logger.error(f"Invalid tunnel type: {tunnel_type}")
            return False, "Invalid tunnel type"

        # Update database with tunnel info
        conn = get_db_connection()
        now = datetime.datetime.now()

        # Calculate end_time based on time_limit
        end_time = None
        if time_limit > 0:  # If not "Forever"
            end_time = now + datetime.timedelta(hours=time_limit)
            logger.info(f"Tunnel will expire at: {end_time}")

        conn.execute('''
        UPDATE tunnels
        SET status = ?, start_time = ?, end_time = ?, public_url = ?, tunnel_id = ?, log_file = ?
        WHERE app_name = ?
        ''', ('running', now, end_time, tunnel.public_url, tunnel.api_url.split('/')[-1], log_file, app_name))
        conn.commit()
        conn.close()

        # Store the tunnel object
        active_tunnels[app_name] = tunnel

        # Start a timer if time limit is not forever
        if time_limit > 0:
            tunnel_timers[app_name] = threading.Timer(time_limit * 3600, stop_tunnel, [app_name, True])
            tunnel_timers[app_name].daemon = True
            tunnel_timers[app_name].start()
            logger.info(f"Set timer for {time_limit} hours")

        # Remove the file handler to avoid duplicate logs
        logger.removeHandler(file_handler)

        return True, tunnel.public_url

    except Exception as e:
        logger.error(f"Error starting tunnel: {str(e)}")
        # Remove the file handler to avoid duplicate logs
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith(log_file):
                logger.removeHandler(handler)
        return False, str(e)

def stop_tunnel(app_name, time_expired=False):
    if app_name in active_tunnels:
        try:
            # Log the action
            conn = get_db_connection()
            log_file = conn.execute('SELECT log_file FROM tunnels WHERE app_name = ?', (app_name,)).fetchone()['log_file']
            conn.close()

            if log_file:
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)

                reason = "time expiration" if time_expired else "manual stop"
                logger.info(f"Stopping tunnel {app_name} due to {reason}")

            # Disconnect the tunnel
            ngrok.disconnect(active_tunnels[app_name].public_url)
            if log_file:
                logger.info(f"Disconnected tunnel {app_name}")

            # Update database
            conn = get_db_connection()
            status = 'time_expired' if time_expired else 'stopped'
            conn.execute('''
            UPDATE tunnels
            SET status = ?, public_url = ?, tunnel_id = ?
            WHERE app_name = ?
            ''', (status, "", "", app_name))
            conn.commit()
            conn.close()

            # Clean up resources
            del active_tunnels[app_name]
            if app_name in tunnel_timers and tunnel_timers[app_name]:
                tunnel_timers[app_name].cancel()
                del tunnel_timers[app_name]

            if log_file:
                logger.info(f"Tunnel {app_name} stopped successfully")
                # Remove the file handler to avoid duplicate logs
                logger.removeHandler(file_handler)

            return True, f"Tunnel {app_name} stopped successfully"
        except Exception as e:
            if log_file:
                logger.error(f"Error stopping tunnel: {str(e)}")
                # Remove the file handler to avoid duplicate logs
                for handler in logger.handlers:
                    if isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith(log_file):
                        logger.removeHandler(handler)
            return False, str(e)
    else:
        return False, f"Tunnel {app_name} not found in active tunnels"

# Background checker for expired tunnels
def check_expired_tunnels():
    while True:
        try:
            conn = get_db_connection()
            now = datetime.datetime.now()

            # Find all tunnels with status 'running' and end_time in the past
            expired_tunnels = conn.execute('''
            SELECT app_name FROM tunnels
            WHERE status = 'running' AND end_time IS NOT NULL AND end_time < ?
            ''', (now,)).fetchall()

            for tunnel in expired_tunnels:
                stop_tunnel(tunnel['app_name'], True)

            conn.close()
        except Exception as e:
            print(f"Error checking expired tunnels: {e}")

        # Check every minute
        time.sleep(60)

# Start the background thread to check for expired tunnels
expired_checker = threading.Thread(target=check_expired_tunnels)
expired_checker.daemon = True
expired_checker.start()

# Route for the main page
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tunnels/<int:id>/log')
def get_tunnel_log(id):
    conn = get_db_connection()
    tunnel = conn.execute('SELECT app_name, log_file FROM tunnels WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not tunnel:
        return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

    if not tunnel['log_file'] or not os.path.exists(tunnel['log_file']):
        return jsonify({'success': False, 'message': 'No log file available for this tunnel'}), 404

    try:
        with open(tunnel['log_file'], 'r') as f:
            log_content = f.read()

        return jsonify({
            'success': True,
            'app_name': tunnel['app_name'],
            'log_content': log_content
        })
    except Exception as e:
        tracer = str(traceback.format_exc())
        return jsonify({'success': False, 'message': str("Error on Loading Logs, Maybe Deleted or Not there\n\n"+tracer)}), 500

# API Routes for Tunnels
@app.route('/api/tunnels', methods=['GET'])
def get_tunnels():
    conn = get_db_connection()
    tunnels = conn.execute('SELECT * FROM tunnels').fetchall()
    conn.close()

    tunnel_list = []
    for tunnel in tunnels:
        # Calculate remaining time for active tunnels
        remaining_time = ""
        if tunnel['status'] == 'running' and tunnel['end_time']:
            now = datetime.datetime.now()
            end_time = datetime.datetime.fromisoformat(tunnel['end_time'])
            if end_time > now:
                diff = end_time - now
                hours, remainder = divmod(diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                remaining_time = f"{hours}h {minutes}m"
            else:
                remaining_time = "Expired"
        elif tunnel['time_limit'] == 0:
            remaining_time = "Forever"

        tunnel_list.append({
            'id': tunnel['id'],
            'app_name': tunnel['app_name'],
            'api_key_name': tunnel['api_key_name'],
            'local_addr': tunnel['local_addr'],
            'tunnel_type': tunnel['tunnel_type'],
            'time_limit': tunnel['time_limit'],
            'status': tunnel['status'],
            'public_url': tunnel['public_url'],
            'remaining_time': remaining_time,
            'has_logs': True if tunnel['log_file'] != "" else False
        })

    return jsonify(tunnel_list)

@app.route('/api/tunnels/<int:id>', methods=['GET'])
def get_tunnel(id):
    conn = get_db_connection()
    tunnel = conn.execute('SELECT * FROM tunnels WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not tunnel:
        return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

    return jsonify(dict(tunnel))

@app.route('/api/tunnels', methods=['POST'])
def create_tunnel():
    data = request.json

    conn = get_db_connection()
    try:
        conn.execute('''
        INSERT INTO tunnels (app_name, api_key_name, local_addr, tunnel_type, time_limit)
        VALUES (?, ?, ?, ?, ?)
        ''', (data['app_name'], data['api_key_name'], data['local_addr'],
              data['tunnel_type'], data['time_limit']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Tunnel configuration created successfully'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'App name already exists'}), 400
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tunnels/<int:id>', methods=['PUT'])
def update_tunnel(id):
    data = request.json

    conn = get_db_connection()
    try:
        # First check if the tunnel exists
        tunnel = conn.execute('SELECT status FROM tunnels WHERE id = ?', (id,)).fetchone()
        if not tunnel:
            conn.close()
            return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

        # Don't allow updates if tunnel is running
        if tunnel['status'] == 'running':
            conn.close()
            return jsonify({'success': False, 'message': 'Stop the tunnel before updating'}), 400

        conn.execute('''
        UPDATE tunnels
        SET app_name = ?, api_key_name = ?, local_addr = ?, tunnel_type = ?, time_limit = ?
        WHERE id = ?
        ''', (data['app_name'], data['api_key_name'], data['local_addr'],
              data['tunnel_type'], data['time_limit'], id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Tunnel updated successfully'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'App name already exists'}), 400
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tunnels/<int:id>', methods=['DELETE'])
def delete_tunnel(id):
    conn = get_db_connection()
    try:
        # Get the app_name before deleting
        tunnel = conn.execute('SELECT app_name, status FROM tunnels WHERE id = ?', (id,)).fetchone()
        if not tunnel:
            conn.close()
            return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

        # Stop the tunnel if it's running
        if tunnel['status'] == 'running':
            stop_tunnel(tunnel['app_name'])

        try:
            log_file = tunnel['log_file']
            if os.path.exists(log_file):
                os.remove(log_file)
        except:
            pass

        conn.execute('DELETE FROM tunnels WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Tunnel deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tunnels/<int:id>/start', methods=['POST'])
def start_tunnel_route(id):
    conn = get_db_connection()
    tunnel = conn.execute('SELECT app_name FROM tunnels WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not tunnel:
        return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

    success, message = start_tunnel(tunnel['app_name'])
    if success:
        return jsonify({'success': True, 'message': 'Tunnel started', 'public_url': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

@app.route('/api/tunnels/<int:id>/stop', methods=['POST'])
def stop_tunnel_route(id):
    conn = get_db_connection()
    tunnel = conn.execute('SELECT app_name FROM tunnels WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not tunnel:
        return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

    success, message = stop_tunnel(tunnel['app_name'])
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

@app.route('/api/tunnels/<int:id>/restart', methods=['POST'])
def restart_tunnel_route(id):
    conn = get_db_connection()
    tunnel = conn.execute('SELECT app_name FROM tunnels WHERE id = ?', (id,)).fetchone()
    conn.close()

    if not tunnel:
        return jsonify({'success': False, 'message': 'Tunnel not found'}), 404

    # Stop first, then start
    app_name = tunnel['app_name']
    if app_name in active_tunnels:
        success, _ = stop_tunnel(app_name)
        if not success:
            return jsonify({'success': False, 'message': 'Failed to stop tunnel for restart'}), 500

    success, message = start_tunnel(app_name)
    if success:
        return jsonify({'success': True, 'message': 'Tunnel restarted', 'public_url': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

# API Routes for API Keys
@app.route('/api/apikeys', methods=['GET'])
def get_api_keys():
    conn = get_db_connection()
    apikeys = conn.execute('SELECT id, name FROM api_keys').fetchall()
    conn.close()

    apikey_list = [{'id': key['id'], 'name': key['name']} for key in apikeys]
    return jsonify(apikey_list)

@app.route('/api/apikeys/full', methods=['GET'])
def get_full_api_keys():
    conn = get_db_connection()
    apikeys = conn.execute('SELECT id, name, api_key FROM api_keys').fetchall()
    conn.close()

    apikey_list = [{'id': key['id'], 'name': key['name'], 'api_key': key['api_key']} for key in apikeys]
    return jsonify(apikey_list)

@app.route('/api/apikeys', methods=['POST'])
def create_api_key():
    data = request.json

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO api_keys (name, api_key) VALUES (?, ?)',
                    (data['name'], data['api_key']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'API key added successfully'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'API key name already exists'}), 400
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/apikeys/<int:id>', methods=['PUT'])
def update_api_key(id):
    data = request.json

    conn = get_db_connection()
    try:
        # First check if key exists
        key = conn.execute('SELECT name FROM api_keys WHERE id = ?', (id,)).fetchone()
        if not key:
            conn.close()
            return jsonify({'success': False, 'message': 'API key not found'}), 404

        old_name = key['name']

        # Update the API key
        conn.execute('UPDATE api_keys SET name = ?, api_key = ? WHERE id = ?',
                    (data['name'], data['api_key'], id))

        # If name changed, update references in tunnels table
        if old_name != data['name']:
            conn.execute('UPDATE tunnels SET api_key_name = ? WHERE api_key_name = ?',
                        (data['name'], old_name))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'API key updated successfully'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'API key name already exists'}), 400
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/apikeys/<int:id>', methods=['DELETE'])
def delete_api_key(id):
    conn = get_db_connection()
    try:
        # Check if key exists
        key = conn.execute('SELECT name FROM api_keys WHERE id = ?', (id,)).fetchone()
        if not key:
            conn.close()
            return jsonify({'success': False, 'message': 'API key not found'}), 404

        # Check if key is in use by any tunnels
        tunnels = conn.execute('SELECT id FROM tunnels WHERE api_key_name = ?',
                              (key['name'],)).fetchall()
        if tunnels:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Cannot delete API key because it is in use by tunnels'
            }), 400

        # Delete the key
        conn.execute('DELETE FROM api_keys WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'API key deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=4141, debug=True)
