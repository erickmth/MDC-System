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
                duration REAL NOT NULL,
                carrinho_id INTEGER
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
                carrinho_id INTEGER,
                UNIQUE(model, operator, carrinho_id)
            )
        ''')
        
        # Tabelas para produção contínua
        conn.execute('''
            CREATE TABLE IF NOT EXISTS carrinhos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modelo TEXT NOT NULL,
                estado TEXT DEFAULT 'em_producao',
                data_criacao TEXT NOT NULL,
                data_finalizacao TEXT,
                operador_atual TEXT DEFAULT 'A1',
                sequencia INTEGER DEFAULT 0
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
                sequencia INTEGER NOT NULL,
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

# Funções auxiliares
def get_previous_operator(operator):
    operators = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']
    index = operators.index(operator)
    return operators[index - 1] if index > 0 else None

def get_next_operator(operator):
    operators = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']
    index = operators.index(operator)
    return operators[index + 1] if index < len(operators) - 1 else None

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

# Endpoint para resetar dados
@app.route('/reset', methods=['POST'])
def reset_all_data():
    try:
        conn = get_db_connection()
        
        # Limpar todas as tabelas
        conn.execute('DELETE FROM alerts')
        conn.execute('DELETE FROM process_times')
        conn.execute('DELETE FROM process_states')
        conn.execute('DELETE FROM carrinhos')
        conn.execute('DELETE FROM carrinho_etapas')
        
        # Reiniciar as sequências dos IDs autoincrement
        conn.execute('DELETE FROM sqlite_sequence WHERE name IN ("alerts", "process_times", "process_states", "carrinhos", "carrinho_etapas")')
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Todos os dados de produção foram resetados com sucesso',
            'tables_cleared': ['alerts', 'process_times', 'process_states', 'carrinhos', 'carrinho_etapas']
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Erro ao resetar dados: {str(e)}'}), 500

# Endpoints de Alertas
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

# Sistema de Produção Contínua
@app.route('/carrinhos/novo', methods=['POST'])
def criar_carrinho():
    try:
        data = request.get_json()
        if not data or 'modelo' not in data:
            return jsonify({'error': 'Modelo não especificado'}), 400
            
        modelo = data['modelo']
        if modelo not in VALID_MODELS:
            return jsonify({'error': 'Modelo inválido'}), 400
            
        data_criacao = datetime.now(timezone.utc).isoformat()
        
        conn = get_db_connection()
        
        # Calcular sequência
        ultima_sequencia = conn.execute(
            'SELECT MAX(sequencia) as max_seq FROM carrinhos WHERE modelo = ?',
            (modelo,)
        ).fetchone()
        
        nova_sequencia = (ultima_sequencia['max_seq'] or 0) + 1
        
        cursor = conn.execute(
            'INSERT INTO carrinhos (modelo, data_criacao, operador_atual, sequencia) VALUES (?, ?, ?, ?)',
            (modelo, data_criacao, 'A1', nova_sequencia)
        )
        carrinho_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Carrinho criado com sucesso',
            'carrinho_id': carrinho_id,
            'modelo': modelo,
            'sequencia': nova_sequencia
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos/disponiveis/<operador>', methods=['GET'])
def get_carrinhos_disponiveis(operador):
    try:
        model = request.args.get('model')
        conn = get_db_connection()
        
        carrinhos_disponiveis = []
        
        if operador == 'A1':
            # A1 pode criar novos carrinhos sempre
            return jsonify({
                'operador': operador,
                'carrinhos_disponiveis': [{'tipo': 'novo'}],
                'quantidade': 1,
                'pode_criar': True
            })
        else:
            # Para outros operadores: carrinhos que terminaram a etapa anterior
            carrinhos_prontos = conn.execute('''
                SELECT c.id, c.modelo, c.sequencia
                FROM carrinhos c
                WHERE c.modelo = ? AND c.estado = 'em_producao'
                AND c.operador_atual = ?
                AND NOT EXISTS (
                    SELECT 1 FROM carrinho_etapas 
                    WHERE carrinho_id = c.id AND operador = ? AND fim IS NULL
                )
            ''', (model, operador, operador)).fetchall()
            
            for carrinho in carrinhos_prontos:
                carrinhos_disponiveis.append({
                    'id': carrinho['id'],
                    'modelo': carrinho['modelo'],
                    'sequencia': carrinho['sequencia']
                })
        
        conn.close()
        
        return jsonify({
            'operador': operador,
            'carrinhos_disponiveis': carrinhos_disponiveis,
            'quantidade': len(carrinhos_disponiveis)
        })
        
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
        carrinho_id = data.get('carrinho_id')
        start_time = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        
        if operator == 'A1':
            # A1 cria novo carrinho
            if carrinho_id:
                return jsonify({'error': 'A1 não pode usar carrinho existente'}), 400
                
            # Calcular sequência
            ultima_sequencia = conn.execute(
                'SELECT MAX(sequencia) as max_seq FROM carrinhos WHERE modelo = ?',
                (model,)
            ).fetchone()
            
            nova_sequencia = (ultima_sequencia['max_seq'] or 0) + 1
            
            cursor = conn.execute(
                'INSERT INTO carrinhos (modelo, data_criacao, operador_atual, sequencia) VALUES (?, ?, ?, ?)',
                (model, start_time, operator, nova_sequencia)
            )
            carrinho_id = cursor.lastrowid
            
            # Registrar primeira etapa
            sequencia_etapa = 1
            conn.execute(
                'INSERT INTO carrinho_etapas (carrinho_id, operador, parte, inicio, sequencia) VALUES (?, ?, ?, ?, ?)',
                (carrinho_id, operator, part, start_time, sequencia_etapa)
            )
        else:
            # Outros operadores usam carrinho existente
            if not carrinho_id:
                return jsonify({'error': 'Carrinho não especificado'}), 400
                
            # Verificar se carrinho existe e está no operador correto
            carrinho = conn.execute(
                'SELECT * FROM carrinhos WHERE id = ? AND modelo = ? AND operador_atual = ?',
                (carrinho_id, model, operator)
            ).fetchone()
            
            if not carrinho:
                return jsonify({'error': 'Carrinho não disponível para este operador'}), 404
            
            # Registrar nova etapa
            ultima_etapa = conn.execute(
                '''SELECT * FROM carrinho_etapas 
                   WHERE carrinho_id = ? 
                   ORDER BY sequencia DESC LIMIT 1''',
                (carrinho_id,)
            ).fetchone()
            
            sequencia_etapa = (ultima_etapa['sequencia'] if ultima_etapa else 0) + 1
            conn.execute(
                'INSERT INTO carrinho_etapas (carrinho_id, operador, parte, inicio, sequencia) VALUES (?, ?, ?, ?, ?)',
                (carrinho_id, operator, part, start_time, sequencia_etapa)
            )

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'Processo iniciado com sucesso',
            'start_time': start_time,
            'carrinho_id': carrinho_id,
            'sequencia_etapa': sequencia_etapa
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
        carrinho_id = data.get('carrinho_id')
        end_time = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        
        # Buscar etapa ativa
        etapa = conn.execute(
            'SELECT * FROM carrinho_etapas WHERE carrinho_id = ? AND operador = ? AND fim IS NULL',
            (carrinho_id, operator)
        ).fetchone()

        if not etapa:
            return jsonify({'error': 'Nenhum processo ativo encontrado'}), 404

        # Calcular duração
        start_time = datetime.fromisoformat(etapa['inicio'])
        end_time_dt = datetime.fromisoformat(end_time)
        duration = (end_time_dt - start_time).total_seconds()

        # Finalizar etapa
        conn.execute(
            'UPDATE carrinho_etapas SET fim = ?, duracao = ? WHERE id = ?',
            (end_time, duration, etapa['id'])
        )

        # Registrar no process_times
        conn.execute(
            'INSERT INTO process_times (model, operator, part, start_time, end_time, duration, carrinho_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (model, operator, part, etapa['inicio'], end_time, duration, carrinho_id)
        )

        # Atualizar operador atual do carrinho
        if operator != 'A6':
            proximo_operador = get_next_operator(operator)
            conn.execute(
                'UPDATE carrinhos SET operador_atual = ? WHERE id = ?',
                (proximo_operador, carrinho_id)
            )
        else:
            # Finalizar carrinho
            conn.execute(
                'UPDATE carrinhos SET estado = "finalizado", data_finalizacao = ? WHERE id = ?',
                (end_time, carrinho_id)
            )

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'Processo finalizado com sucesso',
            'duration': duration,
            'carrinho_id': carrinho_id,
            'proximo_operador': get_next_operator(operator) if operator != 'A6' else None
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoints de Monitoramento
@app.route('/process/status', methods=['GET'])
def get_process_status():
    try:
        model = request.args.get('model')
        conn = get_db_connection()

        # Buscar etapas ativas
        if model:
            etapas_ativas = conn.execute(
                '''SELECT ce.*, c.modelo, c.sequencia
                   FROM carrinho_etapas ce
                   JOIN carrinhos c ON ce.carrinho_id = c.id
                   WHERE c.modelo = ? AND ce.fim IS NULL
                   ORDER BY c.sequencia''',
                (model,)
            ).fetchall()
        else:
            etapas_ativas = conn.execute(
                '''SELECT ce.*, c.modelo, c.sequencia
                   FROM carrinho_etapas ce
                   JOIN carrinhos c ON ce.carrinho_id = c.id
                   WHERE ce.fim IS NULL
                   ORDER BY c.modelo, c.sequencia'''
            ).fetchall()

        processes_list = []
        for etapa in etapas_ativas:
            processes_list.append({
                'carrinho_id': etapa['carrinho_id'],
                'model': etapa['modelo'],
                'operator': etapa['operador'],
                'part': etapa['parte'],
                'is_active': True,
                'start_time': etapa['inicio'],
                'sequencia': etapa['sequencia']
            })

        conn.close()
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
                SELECT pt.*, c.sequencia
                FROM process_times pt
                JOIN carrinhos c ON pt.carrinho_id = c.id
                WHERE pt.model = ?
                ORDER BY c.sequencia, pt.operator
            ''', (model,)).fetchall()
        else:
            times = conn.execute('''
                SELECT pt.*, c.sequencia
                FROM process_times pt
                JOIN carrinhos c ON pt.carrinho_id = c.id
                ORDER BY pt.model, c.sequencia, pt.operator
            ''').fetchall()

        times_list = [
            {
                'id': time['id'],
                'model': time['model'],
                'operator': time['operator'],
                'part': time['part'],
                'start_time': time['start_time'],
                'end_time': time['end_time'],
                'duration': time['duration'],
                'carrinho_id': time['carrinho_id'],
                'sequencia': time['sequencia']
            }
            for time in times
        ]

        conn.close()
        return jsonify(times_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos', methods=['GET'])
def get_carrinhos():
    try:
        modelo = request.args.get('modelo')
        conn = get_db_connection()
        
        if modelo:
            carrinhos = conn.execute(
                'SELECT * FROM carrinhos WHERE modelo = ? ORDER BY sequencia',
                (modelo,)
            ).fetchall()
        else:
            carrinhos = conn.execute(
                'SELECT * FROM carrinhos ORDER BY modelo, sequencia'
            ).fetchall()
            
        carrinhos_list = []
        for carrinho in carrinhos:
            # Calcular tempo total
            tempo_total = conn.execute(
                'SELECT SUM(duracao) as total FROM carrinho_etapas WHERE carrinho_id = ?',
                (carrinho['id'],)
            ).fetchone()
            
            carrinhos_list.append({
                'id': carrinho['id'],
                'modelo': carrinho['modelo'],
                'estado': carrinho['estado'],
                'data_criacao': carrinho['data_criacao'],
                'data_finalizacao': carrinho['data_finalizacao'],
                'operador_atual': carrinho['operador_atual'],
                'sequencia': carrinho['sequencia'],
                'tempo_total': tempo_total['total'] or 0
            })
            
        conn.close()
        return jsonify(carrinhos_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/carrinhos/ativos', methods=['GET'])
def get_carrinhos_ativos():
    try:
        model = request.args.get('model')
        conn = get_db_connection()
        
        if model:
            carrinhos = conn.execute(
                '''SELECT c.*, 
                          (SELECT operador FROM carrinho_etapas WHERE carrinho_id = c.id AND fim IS NULL) as operador_ativo
                   FROM carrinhos c 
                   WHERE c.modelo = ? AND c.estado = 'em_producao'
                   ORDER BY c.sequencia''',
                (model,)
            ).fetchall()
        else:
            carrinhos = conn.execute(
                '''SELECT c.*, 
                          (SELECT operador FROM carrinho_etapas WHERE carrinho_id = c.id AND fim IS NULL) as operador_ativo
                   FROM carrinhos c 
                   WHERE c.estado = 'em_producao'
                   ORDER BY c.modelo, c.sequencia'''
            ).fetchall()
            
        carrinhos_list = []
        for carrinho in carrinhos:
            # Contar etapas concluídas
            etapas_concluidas = conn.execute(
                'SELECT COUNT(*) as count FROM carrinho_etapas WHERE carrinho_id = ? AND fim IS NOT NULL',
                (carrinho['id'],)
            ).fetchone()
            
            carrinhos_list.append({
                'id': carrinho['id'],
                'modelo': carrinho['modelo'],
                'estado': carrinho['estado'],
                'sequencia': carrinho['sequencia'],
                'operador_atual': carrinho['operador_atual'],
                'operador_ativo': carrinho['operador_ativo'],
                'etapas_concluidas': etapas_concluidas['count']
            })
            
        conn.close()
        return jsonify(carrinhos_list)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)