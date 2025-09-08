# Desenvolvido por Erick Matheus
# FORMARE 2025

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime, timezone
import os

app = Flask(__name__)
CORS(app)  # Habilita CORS para todas as rotas

# Configurações
DATABASE = 'alerts.db'
VALID_OPERATORS = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']

# Inicialização do banco de dados
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator TEXT NOT NULL,
                part TEXT NOT NULL,
                started_at TEXT NOT NULL,
                UNIQUE(operator, part)
            )
        ''')
        conn.commit()

# Conexão com o banco
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Validação de payload
def validate_alert_data(data):
    if not data or 'operator' not in data or 'part' not in data:
        return False, "Dados incompletos. Forneça 'operator' e 'part'."

    operator = data['operator']
    part = data['part']

    if operator not in VALID_OPERATORS:
        return False, f"Operador inválido. Deve ser um de: {VALID_OPERATORS}"

    if not part or not isinstance(part, str) or len(part.strip()) == 0:
        return False, "Peça inválida. Deve ser uma string não vazia."

    return True, ""

# Rotas da API
@app.route('/alerts', methods=['GET'])
def get_alerts():
    try:
        conn = get_db_connection()
        alerts = conn.execute('SELECT * FROM alerts ORDER BY started_at DESC').fetchall()
        conn.close()

        alerts_list = [
            {
                'id': alert['id'],
                'operator': alert['operator'],
                'part': alert['part'],
                'started_at': alert['started_at']
            }
            for alert in alerts
        ]

        return jsonify(alerts_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/alerts', methods=['POST'])
def create_alert():
    try:
        data = request.get_json()

        # Validação
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        operator = data['operator']
        part = data['part']
        started_at = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()

        # Verifica se já existe um alerta ativo para o mesmo operador e peça
        existing = conn.execute(
            'SELECT * FROM alerts WHERE operator = ? AND part = ?',
            (operator, part)
        ).fetchone()

        if existing:
            return jsonify({
                'error': f'Já existe uma solicitação ativa para {operator} - {part}'
            }), 409

        # Insere novo alerta
        cursor = conn.execute(
            'INSERT INTO alerts (operator, part, started_at) VALUES (?, ?, ?)',
            (operator, part, started_at)
        )
        conn.commit()

        new_alert = {
            'id': cursor.lastrowid,
            'operator': operator,
            'part': part,
            'started_at': started_at
        }

        conn.close()
        return jsonify(new_alert), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/alerts/stop', methods=['POST'])
def stop_alert():
    try:
        data = request.get_json()

        # Validação
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        operator = data['operator']
        part = data['part']

        conn = get_db_connection()

        # Remove o alerta correspondente
        result = conn.execute(
            'DELETE FROM alerts WHERE operator = ? AND part = ?',
            (operator, part)
        )
        conn.commit()
        conn.close()

        if result.rowcount == 0:
            return jsonify({'error': 'Nenhum alerta ativo encontrado para parar'}), 404

        return jsonify({'message': 'Solicitação parada com sucesso'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/alerts/<int:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    try:
        conn = get_db_connection()

        # Verifica se o alerta existe
        alert = conn.execute(
            'SELECT * FROM alerts WHERE id = ?',
            (alert_id,)
        ).fetchone()

        if not alert:
            return jsonify({'error': 'Alerta não encontrado'}), 404

        # Remove o alerta
        conn.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Alerta removido com sucesso'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Health check
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
