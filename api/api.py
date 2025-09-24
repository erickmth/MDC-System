# Criado por Erick Matheus
# Formare 2025



from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime, timezone
import os

app = Flask(__name__)
CORS(app)

DATABASE = 'alerts.db'
VALID_OPERATORS = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']
VALID_MODELS = ['313', '314']

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                operator TEXT NOT NULL,
                part TEXT NOT NULL,
                started_at TEXT NOT NULL,
                UNIQUE(model, operator, part)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS process_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                operator TEXT NOT NULL,
                part TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration REAL NOT NULL
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS process_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                operator TEXT NOT NULL,
                part TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                start_time TEXT,
                UNIQUE(model, operator)
            )
        ''')
        
        # Novas tabelas para produção contínua e retrabalho
        conn.execute('''
            CREATE TABLE IF NOT EXISTS carrinhos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modelo TEXT NOT NULL,
                estado TEXT DEFAULT 'em_producao',
                data_criacao TEXT NOT NULL,
                data_finalizacao TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS carrinho_etapas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carrinho_id INTEGER NOT NULL,
                operador TEXT NOT NULL,
                parte TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fim TEXT,
                duracao REAL,
                status TEXT DEFAULT 'completo',
                FOREIGN KEY (carrinho_id) REFERENCES carrinhos(id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS retrabalhos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carrinho_id INTEGER NOT NULL,
                operador_solicitante TEXT NOT NULL,
                operador_alvo TEXT NOT NULL,
                parte TEXT NOT NULL,
                motivo TEXT,
                data_solicitacao TEXT NOT NULL,
                status TEXT DEFAULT 'pendente',
                FOREIGN KEY (carrinho_id) REFERENCES carrinhos(id)
            )
        ''')
        
        conn.commit()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def validate_alert_data(data):
    if not data or 'model' not in data or 'operator' not in data or 'part' not in data:
        return False, "Dados incompletos."

    model = data['model']
    operator = data['operator']
    part = data['part']

    if model not in VALID_MODELS:
        return False, f"Modelo inválido."

    if operator not in VALID_OPERATORS:
        return False, f"Operador inválido."

    if not part or not isinstance(part, str) or len(part.strip()) == 0:
        return False, "Peça inválida."

    return True, ""

@app.route('/alerts', methods=['GET'])
def get_alerts():
    try:
        model = request.args.get('model')
        conn = get_db_connection()

        if model:
            alerts = conn.execute(
                'SELECT * FROM alerts WHERE model = ? ORDER BY started_at DESC',
                (model,)
            ).fetchall()
        else:
            alerts = conn.execute('SELECT * FROM alerts ORDER BY started_at DESC').fetchall()

        conn.close()

        alerts_list = [
            {
                'id': alert['id'],
                'model': alert['model'],
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
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        model = data['model']
        operator = data['operator']
        part = data['part']
        started_at = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        existing = conn.execute(
            'SELECT * FROM alerts WHERE model = ? AND operator = ? AND part = ?',
            (model, operator, part)
        ).fetchone()

        if existing:
            return jsonify({
                'error': f'Já existe uma solicitação ativa'
            }), 409

        cursor = conn.execute(
            'INSERT INTO alerts (model, operator, part, started_at) VALUES (?, ?, ?, ?)',
            (model, operator, part, started_at)
        )
        conn.commit()

        new_alert = {
            'id': cursor.lastrowid,
            'model': model,
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
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        model = data['model']
        operator = data['operator']
        part = data['part']

        conn = get_db_connection()
        result = conn.execute(
            'DELETE FROM alerts WHERE model = ? AND operator = ? AND part = ?',
            (model, operator, part)
        )
        conn.commit()
        conn.close()

        if result.rowcount == 0:
            return jsonify({'error': 'Nenhum alerta ativo encontrado'}), 404

        return jsonify({'message': 'Solicitação parada com sucesso'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/alerts/<int:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    try:
        conn = get_db_connection()
        alert = conn.execute(
            'SELECT * FROM alerts WHERE id = ?',
            (alert_id,)
        ).fetchone()

        if not alert:
            return jsonify({'error': 'Alerta não encontrado'}), 404

        conn.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Alerta removido com sucesso'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process/start', methods=['POST'])
def start_process():
    try:
        data = request.get_json()
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        model = data['model']
        operator = data['operator']
        part = data['part']
        start_time = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        existing = conn.execute(
            'SELECT * FROM process_states WHERE model = ? AND operator = ?',
            (model, operator)
        ).fetchone()

        if existing and existing['is_active']:
            return jsonify({
                'error': f'Já existe um processo ativo'
            }), 409

        if existing:
            conn.execute(
                'UPDATE process_states SET is_active = 1, start_time = ? WHERE model = ? AND operator = ?',
                (start_time, model, operator)
            )
        else:
            conn.execute(
                'INSERT INTO process_states (model, operator, part, is_active, start_time) VALUES (?, ?, ?, 1, ?)',
                (model, operator, part, start_time)
            )

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'Processo iniciado com sucesso',
            'start_time': start_time
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process/end', methods=['POST'])
def end_process():
    try:
        data = request.get_json()
        is_valid, error_msg = validate_alert_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        model = data['model']
        operator = data['operator']
        part = data['part']
        end_time = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        process = conn.execute(
            'SELECT * FROM process_states WHERE model = ? AND operator = ? AND is_active = 1',
            (model, operator)
        ).fetchone()

        if not process:
            return jsonify({'error': 'Nenhum processo ativo encontrado'}), 404

        start_time = datetime.fromisoformat(process['start_time'])
        end_time_dt = datetime.fromisoformat(end_time)
        duration = (end_time_dt - start_time).total_seconds()

        conn.execute(
            'INSERT INTO process_times (model, operator, part, start_time, end_time, duration) VALUES (?, ?, ?, ?, ?, ?)',
            (model, operator, part, process['start_time'], end_time, duration)
        )

        conn.execute(
            'UPDATE process_states SET is_active = 0 WHERE model = ? AND operator = ?',
            (model, operator)
        )

        next_operator = get_next_operator(operator)
        if next_operator:
            next_part = get_part_for_operator(next_operator, model)
            next_start_time = datetime.now(timezone.utc).isoformat()

            next_existing = conn.execute(
                'SELECT * FROM process_states WHERE model = ? AND operator = ?',
                (model, next_operator)
            ).fetchone()

            if next_existing:
                conn.execute(
                    'UPDATE process_states SET is_active = 1, start_time = ? WHERE model = ? AND operator = ?',
                    (next_start_time, model, next_operator)
                )
            else:
                conn.execute(
                    'INSERT INTO process_states (model, operator, part, is_active, start_time) VALUES (?, ?, ?, 1, ?)',
                    (model, next_operator, next_part, next_start_time)
                )

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'Processo finalizado com sucesso',
            'duration': duration,
            'next_operator': next_operator
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process/status', methods=['GET'])
def get_process_status():
    try:
        model = request.args.get('model')
        conn = get_db_connection()

        if model:
            processes = conn.execute(
                'SELECT * FROM process_states WHERE model = ? ORDER BY operator',
                (model,)
            ).fetchall()
        else:
            processes = conn.execute('SELECT * FROM process_states ORDER BY model, operator').fetchall()

        conn.close()

        processes_list = [
            {
                'id': process['id'],
                'model': process['model'],
                'operator': process['operator'],
                'part': process['part'],
                'is_active': bool(process['is_active']),
                'start_time': process['start_time']
            }
            for process in processes
        ]

        return jsonify(processes_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process/times', methods=['GET'])
def get_process_times():
    try:
        model = request.args.get('model')
        conn = get_db_connection()

        if model:
            times = conn.execute('''
                SELECT pt.*
                FROM process_times pt
                INNER JOIN (
                    SELECT operator, MAX(end_time) as max_end_time
                    FROM process_times
                    WHERE model = ? AND end_time IS NOT NULL
                    GROUP BY operator
                ) latest ON pt.operator = latest.operator AND pt.end_time = latest.max_end_time
                WHERE pt.model = ?
                ORDER BY pt.operator
            ''', (model, model)).fetchall()
        else:
            times = conn.execute('''
                SELECT pt.*
                FROM process_times pt
                INNER JOIN (
                    SELECT model, operator, MAX(end_time) as max_end_time
                    FROM process_times
                    WHERE end_time IS NOT NULL
                    GROUP BY model, operator
                ) latest ON pt.model = latest.model AND pt.operator = latest.operator AND pt.end_time = latest.max_end_time
                ORDER BY pt.model, pt.operator
            ''').fetchall()

        conn.close()

        times_list = [
            {
                'id': time['id'],
                'model': time['model'],
                'operator': time['operator'],
                'part': time['part'],
                'start_time': time['start_time'],
                'end_time': time['end_time'],
                'duration': time['duration']
            }
            for time in times
        ]

        return jsonify(times_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_next_operator(current_operator):
    operators = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']
    current_index = operators.index(current_operator)
    if current_index < len(operators) - 1:
        return operators[current_index + 1]
    return None

def get_part_for_operator(operator, model):
    if model == '313':
        parts = {
            'A1': 'Eixos',
            'A2': 'Chassi',
            'A3': 'Lanternas',
            'A4': 'Assoalho',
            'A5': 'Rodas',
            'A6': 'Teto'
        }
    else:
        parts = {
            'A1': 'Eixos',
            'A2': 'Chassi',
            'A3': 'Lanternas',
            'A4': 'Motor',
            'A5': 'Rodas',
            'A6': 'Bancos'
        }
    return parts.get(operator, 'Peça não definida')

# Novos endpoints para produção contínua e retrabalho
@app.route('/carrinhos/iniciar', methods=['POST'])
def iniciar_carrinho():
    try:
        data = request.get_json()
        if not data or 'modelo' not in data:
            return jsonify({'error': 'Modelo não especificado'}), 400
            
        modelo = data['modelo']
        if modelo not in VALID_MODELS:
            return jsonify({'error': 'Modelo inválido'}), 400
            
        data_criacao = datetime.now(timezone.utc).isoformat()
        
        conn = get_db_connection()
        cursor = conn.execute(
            'INSERT INTO carrinhos (modelo, data_criacao) VALUES (?, ?)',
            (modelo, data_criacao)
        )
        carrinho_id = cursor.lastrowid
        
        # Iniciar primeira etapa (A1)
        parte = get_part_for_operator('A1', modelo)
        conn.execute(
            'INSERT INTO carrinho_etapas (carrinho_id, operador, parte, inicio) VALUES (?, ?, ?, ?)',
            (carrinho_id, 'A1', parte, data_criacao)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Carrinho iniciado com sucesso',
            'carrinho_id': carrinho_id,
            'modelo': modelo
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos', methods=['GET'])
def listar_carrinhos():
    try:
        modelo = request.args.get('modelo')
        conn = get_db_connection()
        
        if modelo:
            carrinhos = conn.execute(
                'SELECT * FROM carrinhos WHERE modelo = ? ORDER BY data_criacao DESC',
                (modelo,)
            ).fetchall()
        else:
            carrinhos = conn.execute(
                'SELECT * FROM carrinhos ORDER BY data_criacao DESC'
            ).fetchall()
            
        carrinhos_list = []
        for carrinho in carrinhos:
            # Buscar etapa atual
            etapa_atual = conn.execute(
                '''SELECT operador, parte, inicio, fim, duracao, status 
                   FROM carrinho_etapas 
                   WHERE carrinho_id = ? 
                   ORDER BY id DESC LIMIT 1''',
                (carrinho['id'],)
            ).fetchone()
            
            # Calcular tempo total
            tempo_total = conn.execute(
                '''SELECT SUM(duracao) as total 
                   FROM carrinho_etapas 
                   WHERE carrinho_id = ? AND duracao IS NOT NULL''',
                (carrinho['id'],)
            ).fetchone()
            
            carrinhos_list.append({
                'id': carrinho['id'],
                'modelo': carrinho['modelo'],
                'estado': carrinho['estado'],
                'data_criacao': carrinho['data_criacao'],
                'data_finalizacao': carrinho['data_finalizacao'],
                'etapa_atual': {
                    'operador': etapa_atual['operador'] if etapa_atual else None,
                    'parte': etapa_atual['parte'] if etapa_atual else None,
                    'inicio': etapa_atual['inicio'] if etapa_atual else None,
                    'fim': etapa_atual['fim'] if etapa_atual else None,
                    'status': etapa_atual['status'] if etapa_atual else None
                },
                'tempo_total': tempo_total['total'] if tempo_total and tempo_total['total'] else 0
            })
            
        conn.close()
        return jsonify(carrinhos_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos/<int:carrinho_id>', methods=['GET'])
def detalhes_carrinho(carrinho_id):
    try:
        conn = get_db_connection()
        
        carrinho = conn.execute(
            'SELECT * FROM carrinhos WHERE id = ?',
            (carrinho_id,)
        ).fetchone()
        
        if not carrinho:
            return jsonify({'error': 'Carrinho não encontrado'}), 404
            
        etapas = conn.execute(
            '''SELECT * FROM carrinho_etapas 
               WHERE carrinho_id = ? 
               ORDER BY inicio''',
            (carrinho_id,)
        ).fetchall()
        
        retrabalhos = conn.execute(
            '''SELECT * FROM retrabalhos 
               WHERE carrinho_id = ? 
               ORDER BY data_solicitacao DESC''',
            (carrinho_id,)
        ).fetchall()
        
        conn.close()
        
        etapas_list = [dict(etapa) for etapa in etapas]
        retrabalhos_list = [dict(retrabalho) for retrabalho in retrabalhos]
        
        return jsonify({
            'carrinho': dict(carrinho),
            'etapas': etapas_list,
            'retrabalhos': retrabalhos_list
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos/<int:carrinho_id>/avancar', methods=['POST'])
def avancar_etapa(carrinho_id):
    try:
        data = request.get_json()
        if not data or 'operador' not in data or 'parte' not in data:
            return jsonify({'error': 'Dados incompletos'}), 400
            
        operador = data['operador']
        parte = data['parte']
        
        conn = get_db_connection()
        
        # Verificar se carrinho existe
        carrinho = conn.execute(
            'SELECT * FROM carrinhos WHERE id = ?',
            (carrinho_id,)
        ).fetchone()
        
        if not carrinho:
            return jsonify({'error': 'Carrinho não encontrado'}), 404
            
        # Finalizar etapa atual
        etapa_atual = conn.execute(
            '''SELECT * FROM carrinho_etapas 
               WHERE carrinho_id = ? AND fim IS NULL 
               ORDER BY id DESC LIMIT 1''',
            (carrinho_id,)
        ).fetchone()
        
        if etapa_atual:
            fim_etapa = datetime.now(timezone.utc).isoformat()
            inicio_etapa = datetime.fromisoformat(etapa_atual['inicio'])
            duracao = (datetime.fromisoformat(fim_etapa) - inicio_etapa).total_seconds()
            
            conn.execute(
                '''UPDATE carrinho_etapas 
                   SET fim = ?, duracao = ? 
                   WHERE id = ?''',
                (fim_etapa, duracao, etapa_atual['id'])
            )
        
        # Iniciar próxima etapa
        inicio_etapa = datetime.now(timezone.utc).isoformat()
        conn.execute(
            '''INSERT INTO carrinho_etapas 
               (carrinho_id, operador, parte, inicio) 
               VALUES (?, ?, ?, ?)''',
            (carrinho_id, operador, parte, inicio_etapa)
        )
        
        # Se for a última etapa, finalizar carrinho
        if operador == 'A6':
            data_finalizacao = datetime.now(timezone.utc).isoformat()
            conn.execute(
                'UPDATE carrinhos SET estado = "finalizado", data_finalizacao = ? WHERE id = ?',
                (data_finalizacao, carrinho_id)
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Etapa avançada com sucesso'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/retrabalho', methods=['POST'])
def solicitar_retrabalho():
    try:
        data = request.get_json()
        required_fields = ['carrinho_id', 'operador_solicitante', 'operador_alvo', 'parte', 'motivo']
        
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Campo {field} não especificado'}), 400
                
        data_solicitacao = datetime.now(timezone.utc).isoformat()
        
        conn = get_db_connection()
        
        # Verificar se carrinho existe
        carrinho = conn.execute(
            'SELECT * FROM carrinhos WHERE id = ?',
            (data['carrinho_id'],)
        ).fetchone()
        
        if not carrinho:
            return jsonify({'error': 'Carrinho não encontrado'}), 404
            
        # Inserir solicitação de retrabalho
        cursor = conn.execute(
            '''INSERT INTO retrabalhos 
               (carrinho_id, operador_solicitante, operador_alvo, parte, motivo, data_solicitacao) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (data['carrinho_id'], data['operador_solicitante'], 
             data['operador_alvo'], data['parte'], data['motivo'], data_solicitacao)
        )
        
        # Atualizar estado do carrinho
        conn.execute(
            'UPDATE carrinhos SET estado = "em_retrabalho" WHERE id = ?',
            (data['carrinho_id'],)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Solicitação de retrabalho registrada com sucesso',
            'retrabalho_id': cursor.lastrowid
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/retrabalhos', methods=['GET'])
def listar_retrabalhos():
    try:
        status = request.args.get('status', 'pendente')
        conn = get_db_connection()
        
        retrabalhos = conn.execute(
            '''SELECT r.*, c.modelo 
               FROM retrabalhos r 
               JOIN carrinhos c ON r.carrinho_id = c.id 
               WHERE r.status = ? 
               ORDER BY r.data_solicitacao DESC''',
            (status,)
        ).fetchall()
        
        conn.close()
        
        retrabalhos_list = [dict(retrabalho) for retrabalho in retrabalhos]
        return jsonify(retrabalhos_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/retrabalho/<int:retrabalho_id>/resolver', methods=['POST'])
def resolver_retrabalho(retrabalho_id):
    try:
        conn = get_db_connection()
        
        # Verificar se retrabalho existe
        retrabalho = conn.execute(
            'SELECT * FROM retrabalhos WHERE id = ?',
            (retrabalho_id,)
        ).fetchone()
        
        if not retrabalho:
            return jsonify({'error': 'Solicitação de retrabalho não encontrada'}), 404
            
        # Atualizar status do retrabalho
        conn.execute(
            'UPDATE retrabalhos SET status = "resolvido" WHERE id = ?',
            (retrabalho_id,)
        )
        
        # Verificar se ainda há retrabalhos pendentes para este carrinho
        retrabalhos_pendentes = conn.execute(
            'SELECT COUNT(*) as count FROM retrabalhos WHERE carrinho_id = ? AND status = "pendente"',
            (retrabalho['carrinho_id'],)
        ).fetchone()
        
        # Se não houver mais retrabalhos pendentes, voltar carrinho para produção
        if retrabalhos_pendentes['count'] == 0:
            conn.execute(
                'UPDATE carrinhos SET estado = "em_producao" WHERE id = ?',
                (retrabalho['carrinho_id'],)
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Retrabalho resolvido com sucesso'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
