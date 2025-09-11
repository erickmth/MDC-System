import serial
import tkinter as tk
from tkinter import ttk, messagebox
import time
import csv
from datetime import datetime
import math
import threading
from PIL import Image, ImageTk
import os
import json
import tempfile
import atexit

# ---------------- CONFIGURAÇÕES ----------------
PORTA_SERIAL = 'COM6'  
BAUD_RATE = 9600

# IDs cadastrados
operadores = {
    "056B4A806403E9": "Operador Suporte",
    "AD88C801": "Raquel",
}

# IDs de administradores
administradores = {
    "3A163602": "Admin Erick",
}

# Mapeamento de áreas para peças - Modelo 314
areas_pecas_314 = {
    "A1": "Eixos",
    "A2": "Chassi",
    "A3": "Lanternas",
    "A4": "Parabrisas",
    "A5": "Rodas",
    "A6": "Teto"
}

# Mapeamento de áreas para peças - Modelo 313
areas_pecas_313 = {
    "A1": "Eixos",
    "A2": "Chassi",
    "A3": "Lanternas",
    "A4": "Assoalho",
    "A5": "Rodas",
    "A6": "Teto"
}

# Estoque inicial (será carregado/salvo durante a execução)
estoque_314 = {
    "A1": {"peca": "Eixos", "quantidade": 100, "minimo": 20},
    "A2": {"peca": "Chassi", "quantidade": 50, "minimo": 10},
    "A3": {"peca": "Lanternas", "quantidade": 200, "minimo": 30},
    "A4": {"peca": "Parabrisas", "quantidade": 30, "minimo": 5},
    "A5": {"peca": "Rodas", "quantidade": 80, "minimo": 15},
    "A6": {"peca": "Teto", "quantidade": 25, "minimo": 5}
}

estoque_313 = {
    "A1": {"peca": "Eixos", "quantidade": 100, "minimo": 20},
    "A2": {"peca": "Chassi", "quantidade": 50, "minimo": 10},
    "A3": {"peca": "Lanternas", "quantidade": 200, "minimo": 30},
    "A4": {"peca": "Assoalho", "quantidade": 30, "minimo": 5},
    "A5": {"peca": "Rodas", "quantidade": 80, "minimo": 15},
    "A6": {"peca": "Teto", "quantidade": 25, "minimo": 5}
}

# ---------------- VARIÁVEIS GLOBAIS ----------------
area_var = None
peca_var = None
quantidade_entry = None
form_frame = None
ultimo_rfid_lido = None
ultimo_tempo_leitura = 0
bloquear_leitura = False
wave_offset = 0  # Para animação
ser = None
serial_thread = None
running = True
last_activity_time = time.time()
wave_animation_active = False
logout_timer = None
status_label = None
wave_canvas = None
estoque_frame = None
current_user = None
current_user_role = None  # 'admin', 'operador'
current_model = None  # '313' ou '314'
areas_pecas = None  # Será definido dinamicamente
estoque = None  # Será definido dinamicamente
pending_callbacks = {}  # Para gerenciar callbacks agendados

# Dicionário para manter referências das imagens (evita garbage collection)
IMAGES = {}

# ---------------- FUNÇÕES DE ESTOQUE ----------------

def carregar_estoque():
    """Carrega o estoque de um arquivo temporário se existir"""
    global estoque_313, estoque_314
    try:
        if os.path.exists('estoque_temp_313.json'):
            with open('estoque_temp_313.json', 'r') as f:
                loaded_data = json.load(f)
                # Garantir que os valores sejam inteiros
                for area, dados in loaded_data.items():
                    if isinstance(dados, dict):
                        dados["quantidade"] = int(dados.get("quantidade", 0))
                        dados["minimo"] = int(dados.get("minimo", 0))
                estoque_313 = loaded_data
            print("Estoque 313 carregado do arquivo temporário")
        
        if os.path.exists('estoque_temp_314.json'):
            with open('estoque_temp_314.json', 'r') as f:
                loaded_data = json.load(f)
                # Garantir que os valores sejam inteiros
                for area, dados in loaded_data.items():
                    if isinstance(dados, dict):
                        dados["quantidade"] = int(dados.get("quantidade", 0))
                        dados["minimo"] = int(dados.get("minimo", 0))
                estoque_314 = loaded_data
            print("Estoque 314 carregado do arquivo temporário")
    except Exception as e:
        print(f"Erro ao carregar estoque: {e}")

def salvar_estoque():
    """Salva o estoque em arquivos temporários de forma atômica"""
    try:
        # Salvar estoque 313
        temp_file_313 = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(estoque_313, temp_file_313)
        temp_file_313.close()
        os.replace(temp_file_313.name, 'estoque_temp_313.json')
        print("Estoque 313 salvo no arquivo temporário")
        
        # Salvar estoque 314
        temp_file_314 = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(estoque_314, temp_file_314)
        temp_file_314.close()
        os.replace(temp_file_314.name, 'estoque_temp_314.json')
        print("Estoque 314 salvo no arquivo temporário")
    except Exception as e:
        print(f"Erro ao salvar estoque: {e}")

def atualizar_estoque(area, quantidade):
    """Atualiza o estoque após uma reposição (SUBTRAI)"""
    global estoque
    
    if area in estoque:
        # Verificar se há estoque suficiente antes de subtrair
        if estoque[area]["quantidade"] >= quantidade:
            estoque[area]["quantidade"] -= quantidade
            salvar_estoque()
            return True
        else:
            print(f"Erro: Estoque insuficiente em {area}. Disponível: {estoque[area]['quantidade']}, Solicitado: {quantidade}")
            return False
    return False

def verificar_estoque_minimo():
    """Verifica se algum item está abaixo do estoque mínimo"""
    alertas = []
    for area, dados in estoque.items():
        if dados["quantidade"] <= dados["minimo"]:
            alertas.append(f"{area} ({dados['peca']}): {dados['quantidade']} unidades (mínimo: {dados['minimo']})")
    return alertas

# ---------------- FUNÇÕES PRINCIPAIS ----------------

def cancel_pending_callbacks():
    """Cancela todos os callbacks pendentes"""
    global pending_callbacks
    for callback_id in list(pending_callbacks.keys()):
        try:
            root.after_cancel(callback_id)
        except:
            pass
    pending_callbacks = {}

def schedule_callback(delay_ms, callback, *args):
    """Agenda um callback e retorna seu ID"""
    callback_id = root.after(delay_ms, callback, *args)
    pending_callbacks[callback_id] = True
    return callback_id

def cancel_callback(callback_id):
    """Cancela um callback específico"""
    if callback_id in pending_callbacks:
        try:
            root.after_cancel(callback_id)
            del pending_callbacks[callback_id]
        except:
            pass

def reset_inactivity_timer():
    """Reinicia o timer de inatividade"""
    global last_activity_time, logout_timer
    last_activity_time = time.time()
    
    # Cancela o timer anterior se existir
    if logout_timer:
        try:
            root.after_cancel(logout_timer)
            if logout_timer in pending_callbacks:
                del pending_callbacks[logout_timer]
        except:
            pass
    
    # Agenda novo logout para 60 segundos (apenas se estiver logado)
    if current_user:
        logout_timer = schedule_callback(60000, logout_by_inactivity)

def logout_by_inactivity():
    """Desloga por inatividade"""
    global bloquear_leitura, current_user, current_user_role, current_model
    if not current_user:
        return  # Já está na tela inicial
    
    messagebox.showinfo("Sessão Expirada", "Sessão encerrada por inatividade.")
    current_user = None
    current_user_role = None
    current_model = None
    voltar_tela_inicial()

def salvar_reposicao(nome, area, peca, quantidade, modelo):
    """Salva os dados em CSV com tratamento de erro"""
    try:
        file_exists = os.path.exists('reposicoes.csv')
        with open('reposicoes.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Data/Hora", "Nome", "Área", "Peça", "Quantidade", "Modelo"])
            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nome, area, peca, quantidade, modelo])
        return True
    except Exception as e:
        print(f"Erro ao salvar reposição: {e}")
        messagebox.showerror("Erro", f"Não foi possível salvar a reposição: {e}")
        return False

def mostrar_selecao_modelo(nome, role):
    """Exibe a tela de seleção de modelo"""
    global bloquear_leitura, wave_animation_active, current_user, current_user_role
    
    bloquear_leitura = True
    wave_animation_active = False
    current_user = nome
    current_user_role = role
    
    for widget in root.winfo_children():
        widget.destroy()
    
    # Frame principal
    main_frame = tk.Frame(root, bg='white')
    main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # Título
    title_frame = tk.Frame(main_frame, bg='white')
    title_frame.pack(fill=tk.X, pady=(0, 30))
    
    tk.Label(title_frame, text=f"Seleção de Modelo", 
             font=("Arial", 18, "bold"), bg='white', fg='#2c3e50').pack(pady=(10, 5))
    tk.Label(title_frame, text=f"{role.capitalize()}: {nome}", 
             font=("Arial", 12), bg='white', fg='#7f8c8d').pack()
    
    # Frame para botões de modelo
    model_frame = tk.Frame(main_frame, bg='white')
    model_frame.pack(fill=tk.BOTH, expand=True, pady=50)
    
    # Botão Modelo 313
    btn_313 = tk.Button(model_frame, text="Modelo 313", 
                        command=lambda: selecionar_modelo("313", nome, role),
                        font=("Arial", 14), bg='#3498db', fg='white',
                        width=20, height=2)
    btn_313.pack(pady=20)
    
    # Botão Modelo 314
    btn_314 = tk.Button(model_frame, text="Modelo 314", 
                        command=lambda: selecionar_modelo("314", nome, role),
                        font=("Arial", 14), bg='#3498db', fg='white',
                        width=20, height=2)
    btn_314.pack(pady=20)
    
    # Botão Voltar
    back_btn = tk.Button(main_frame, text="Voltar", 
                         command=voltar_tela_inicial,
                         font=("Arial", 12), bg='#e74c3c', fg='white')
    back_btn.pack(side=tk.BOTTOM, pady=20)
    
    reset_inactivity_timer()

def selecionar_modelo(modelo, nome, role):
    """Seleciona o modelo e redireciona para a tela apropriada"""
    global current_model, areas_pecas, estoque
    
    current_model = modelo
    
    if modelo == "313":
        areas_pecas = areas_pecas_313
        estoque = estoque_313
    else:
        areas_pecas = areas_pecas_314
        estoque = estoque_314
    
    if role == "admin":
        mostrar_painel_administrativo(nome)
    else:
        mostrar_formulario(nome)

def mostrar_formulario(nome):
    """Exibe o formulário de reposição"""
    global area_var, peca_var, quantidade_entry, bloquear_leitura, wave_animation_active, current_user
    
    bloquear_leitura = True
    wave_animation_active = False
    current_user = nome
    
    for widget in root.winfo_children():
        widget.destroy()
    
    # Frame principal
    main_frame = tk.Frame(root, bg='white')
    main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # Título
    title_frame = tk.Frame(main_frame, bg='white')
    title_frame.pack(fill=tk.X, pady=(0, 20))
    
    modelo_text = f"Modelo {current_model}" if current_model else "Modelo não selecionado"
    
    tk.Label(title_frame, text=f"Registro de Reposição", 
             font=("Arial", 18, "bold"), bg='white', fg='#2c3e50').pack(pady=(10, 5))
    tk.Label(title_frame, text=f"Operador: {nome} | {modelo_text}", 
             font=("Arial", 12), bg='white', fg='#7f8c8d').pack()
    
    # Exibir alertas de estoque mínimo
    alertas = verificar_estoque_minimo()
    if alertas:
        alert_frame = tk.Frame(main_frame, bg='#fff3cd', relief=tk.RAISED, bd=1)
        alert_frame.pack(fill=tk.X, pady=(0, 20))
        tk.Label(alert_frame, text="⚠️ ALERTA: Estoque mínimo atingido:", 
                font=("Arial", 10, "bold"), bg='#fff3cd', fg='#856404').pack(anchor=tk.W, padx=10, pady=5)
        for alerta in alertas:
            tk.Label(alert_frame, text=f"• {alerta}", 
                    font=("Arial", 9), bg='#fff3cd', fg='#856404').pack(anchor=tk.W, padx=20, pady=2)
    
    # Formulário
    form_frame = tk.Frame(main_frame, bg='white')
    form_frame.pack(fill=tk.BOTH, expand=True)
    
    # Área
    area_frame = tk.Frame(form_frame, bg='white')
    area_frame.pack(fill=tk.X, pady=10)
    tk.Label(area_frame, text="Área de reposição:", font=("Arial", 12), 
             bg='white', fg='#2c3e50').pack(anchor=tk.W)
    area_var = tk.StringVar()
    
    area_cb = ttk.Combobox(area_frame, textvariable=area_var, 
                           values=list(areas_pecas.keys()), 
                           state="readonly", font=("Arial", 12))
    area_cb.pack(fill=tk.X, pady=(5, 0))
    area_cb.bind('<<ComboboxSelected>>', atualizar_peca)
    
    # Peça
    peca_frame = tk.Frame(form_frame, bg='white')
    peca_frame.pack(fill=tk.X, pady=10)
    tk.Label(peca_frame, text="Peça a repor:", font=("Arial", 12), 
             bg='white', fg='#2c3e50').pack(anchor=tk.W)
    
    peca_info_frame = tk.Frame(peca_frame, bg='white')
    peca_info_frame.pack(fill=tk.X, pady=(5, 0))
    
    peca_var = tk.StringVar(value="Selecione uma área")
    tk.Label(peca_info_frame, textvariable=peca_var, font=("Arial", 12, "bold"), 
             foreground="#3498db", bg='white').pack(side=tk.LEFT)
    
    # Label para mostrar estoque atual e mínimo
    estoque_label = tk.Label(peca_info_frame, text="", font=("Arial", 10), 
                            foreground="#7f8c8d", bg='white')
    estoque_label.pack(side=tk.RIGHT)
    
    def atualizar_estoque_display(event=None):
        area = area_var.get()
        if area in estoque:
            estoque_atual = estoque[area]["quantidade"]
            minimo = estoque[area]["minimo"]
            cor = "#e74c3c" if estoque_atual <= minimo else "#27ae60"
            estoque_label.config(
                text=f"Estoque: {estoque_atual} | Mínimo: {minimo}",
                fg=cor
            )
        else:
            estoque_label.config(text="")
    
    area_var.trace('w', lambda *args: atualizar_estoque_display())
    
    # Quantidade
    quantidade_frame = tk.Frame(form_frame, bg='white')
    quantidade_frame.pack(fill=tk.X, pady=10)
    
    quantidade_header_frame = tk.Frame(quantidade_frame, bg='white')
    quantidade_header_frame.pack(fill=tk.X)
    
    tk.Label(quantidade_header_frame, text="Quantidade:", font=("Arial", 12), 
             bg='white', fg='#2c3e50').pack(side=tk.LEFT)
    
    # Label para mostrar o mínimo necessário
    minimo_label = tk.Label(quantidade_header_frame, text="", font=("Arial", 10, "bold"), 
                           foreground="#e67e22", bg='white')
    minimo_label.pack(side=tk.RIGHT)
    
    def atualizar_minimo_display(event=None):
        area = area_var.get()
        if area in estoque:
            minimo = estoque[area]["minimo"]
            minimo_label.config(text=f"Mínimo: {minimo} peças")
        else:
            minimo_label.config(text="")
    
    area_var.trace('w', lambda *args: atualizar_minimo_display())
    
    # Usar tk.Spinbox como fallback se ttk.Spinbox não estiver disponível
    try:
        quantidade_entry = ttk.Spinbox(quantidade_frame, from_=1, to=1000, 
                                      font=("Arial", 12), width=10)
    except:
        quantidade_entry = tk.Spinbox(quantidade_frame, from_=1, to=1000, 
                                     font=("Arial", 12), width=10)
    
    quantidade_entry.pack(anchor=tk.W, pady=(5, 0))
    quantidade_entry.delete(0, tk.END)
    quantidade_entry.insert(0, "1")
    
    # Botões
    button_frame = tk.Frame(form_frame, bg='white')
    button_frame.pack(fill=tk.X, pady=(20, 0))
    
    # Botão Voltar
    cancel_btn = tk.Button(button_frame, text="Voltar", 
               command=lambda: mostrar_selecao_modelo(nome, "operador"),
               font=("Arial", 12), bg='#e74c3c', fg='white')
    cancel_btn.pack(side=tk.LEFT, padx=(0, 10))
    
    register_btn = tk.Button(button_frame, text="Registrar",
               command=lambda: registrar_reposicao(nome),
               font=("Arial", 12), bg='#2ecc71', fg='white')
    register_btn.pack(side=tk.RIGHT)
    
    area_cb.focus()
    reset_inactivity_timer()

def atualizar_peca(event=None):
    """Atualiza a peça de acordo com a área"""
    area = area_var.get()
    if area in areas_pecas:
        peca_var.set(areas_pecas[area])
    reset_inactivity_timer()

def registrar_reposicao(nome):
    """Registra reposição"""
    area = area_var.get()
    peca = peca_var.get()
    try:
        quantidade = int(quantidade_entry.get())
        if quantidade <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Erro", "Quantidade inválida!")
        return
    if not area or peca == "Selecione uma área":
        messagebox.showerror("Erro", "Selecione uma área!")
        return
    
    # Verifica se há estoque suficiente
    if area in estoque and estoque[area]["quantidade"] < quantidade:
        messagebox.showerror("Erro", f"Estoque insuficiente! Disponível: {estoque[area]['quantidade']}")
        return
    
    # Salva a reposição e atualiza o estoque
    if salvar_reposicao(nome, area, peca, quantidade, current_model):
        if atualizar_estoque(area, quantidade):
            messagebox.showinfo("Sucesso", f"Reposição registrada com sucesso!\n{quantidade} {peca} removidos do estoque.")
        else:
            messagebox.showerror("Erro", "Não foi possível atualizar o estoque!")
            return
    
    # Volta para a seleção de modelo
    mostrar_selecao_modelo(nome, "operador")

def mostrar_painel_administrativo(nome):
    """Exibe o painel administrativo"""
    global bloquear_leitura, wave_animation_active, current_user, current_user_role
    
    bloquear_leitura = True
    wave_animation_active = False
    current_user = nome
    current_user_role = "admin"
    
    for widget in root.winfo_children():
        widget.destroy()
    
    # Frame principal
    main_frame = tk.Frame(root, bg='white')
    main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # Cabeçalho
    header_frame = tk.Frame(main_frame, bg='white')
    header_frame.pack(fill=tk.X, pady=(0, 20))
    
    modelo_text = f"Modelo {current_model}" if current_model else "Modelo não selecionado"
    
    tk.Label(header_frame, text="Painel Administrativo", 
             font=("Arial", 18, "bold"), bg='white', fg='#2c3e50').pack(pady=(10, 5))
    tk.Label(header_frame, text=f"Administrador: {nome} | {modelo_text}", 
             font=("Arial", 12), bg='white', fg='#7f8c8d').pack()
    
    # Abas
    notebook = ttk.Notebook(main_frame)
    notebook.pack(fill=tk.BOTH, expand=True, pady=10)
    
    # Frame para o estoque do modelo selecionado
    estoque_frame = tk.Frame(notebook, bg='white')
    notebook.add(estoque_frame, text=f"Estoque Modelo {current_model}")
    
    # Tabela de estoque
    columns = ("Área", "Peça", "Quantidade", "Mínimo", "Status")
    tree = ttk.Treeview(estoque_frame, columns=columns, show="headings", height=8)
    
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=100, anchor=tk.CENTER)
    
    tree.column("Peça", width=120)
    tree.column("Status", width=120)
    
    # Scrollbar para a tabela
    scrollbar_table = ttk.Scrollbar(estoque_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar_table.set)
    
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
    scrollbar_table.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Atualizar tabela
    atualizar_tabela_estoque(tree, estoque)
    
    # Frame para adicionar/editar item
    novo_item_frame = tk.Frame(estoque_frame, bg='white')
    novo_item_frame.pack(fill=tk.X, pady=10)
    
    tk.Label(novo_item_frame, text=f"Definir Estoque Mínimo - Modelo {current_model}:", 
             font=("Arial", 10, "bold"), bg='white').pack(anchor=tk.W, pady=(10, 5))
    
    form_frame = tk.Frame(novo_item_frame, bg='white')
    form_frame.pack(fill=tk.X, pady=5)
    
    # Linha 1: Área e Peça
    tk.Label(form_frame, text="Área:", bg='white', font=("Arial", 10)).grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
    area_entry = ttk.Combobox(form_frame, values=list(areas_pecas.keys()), width=8, state="readonly", font=("Arial", 10))
    area_entry.grid(row=0, column=1, padx=5, pady=2)
    
    tk.Label(form_frame, text="Peça:", bg='white', font=("Arial", 10)).grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
    peca_var_admin = tk.StringVar()
    peca_label = tk.Label(form_frame, textvariable=peca_var_admin, bg='white', width=15, anchor=tk.W, font=("Arial", 10))
    peca_label.grid(row=0, column=3, padx=5, pady=2, sticky=tk.W)
    
    # Linha 2: Quantidade e Mínimo
    tk.Label(form_frame, text="Quantidade Atual:", bg='white', font=("Arial", 10)).grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
    
    # Usar tk.Spinbox como fallback se ttk.Spinbox não estiver disponível
    try:
        quant_entry = ttk.Spinbox(form_frame, from_=0, to=10000, width=8, font=("Arial", 10))
    except:
        quant_entry = tk.Spinbox(form_frame, from_=0, to=10000, width=8, font=("Arial", 10))
    
    quant_entry.grid(row=1, column=1, padx=5, pady=2)
    
    tk.Label(form_frame, text="Mínimo Necessário:", bg='white', font=("Arial", 10)).grid(row=1, column=2, padx=5, pady=2, sticky=tk.W)
    
    # Usar tk.Spinbox como fallback se ttk.Spinbox não estiver disponível
    try:
        min_entry = ttk.Spinbox(form_frame, from_=0, to=1000, width=8, font=("Arial", 10))
    except:
        min_entry = tk.Spinbox(form_frame, from_=0, to=1000, width=8, font=("Arial", 10))
    
    min_entry.grid(row=1, column=3, padx=5, pady=2)
    
    # Linha 3: Botão Salvar
    save_button = tk.Button(form_frame, text="Salvar Configuração", 
              command=lambda: salvar_configuracao_admin(area_entry, quant_entry, min_entry, tree),
              font=("Arial", 10), bg='#3498db', fg='white')
    save_button.grid(row=2, column=0, columnspan=4, pady=10)
    
    def atualizar_peca_admin(event=None):
        area = area_entry.get()
        if area in areas_pecas:
            peca_var_admin.set(areas_pecas[area])
    
    area_entry.bind('<<ComboboxSelected>>', atualizar_peca_admin)
    
    def carregar_dados_area():
        area = area_entry.get()
        if area in estoque:
            quant_entry.delete(0, tk.END)
            quant_entry.insert(0, str(estoque[area]["quantidade"]))
            min_entry.delete(0, tk.END)
            min_entry.insert(0, str(estoque[area]["minimo"]))
    
    area_entry.bind('<<ComboboxSelected>>', lambda e: carregar_dados_area())
    
    # Botão Voltar
    button_frame = tk.Frame(main_frame, bg='white')
    button_frame.pack(fill=tk.X, pady=10)
    
    back_button = tk.Button(button_frame, text="Voltar", 
              command=lambda: mostrar_selecao_modelo(nome, "admin"),
              font=("Arial", 12), bg='#e74c3c', fg='white')
    back_button.pack(side=tk.RIGHT)
    
    reset_inactivity_timer()

def atualizar_tabela_estoque(tree, estoque_data):
    """Atualiza a tabela de estoque"""
    for item in tree.get_children():
        tree.delete(item)
    
    for area, dados in sorted(estoque_data.items()):
        status = "✅ Suficiente" if dados["quantidade"] > dados["minimo"] else "⚠️ Abaixo do mínimo"
        tree.insert("", tk.END, values=(
            area, 
            dados["peca"], 
            dados["quantidade"], 
            dados["minimo"],
            status
        ))

def salvar_configuracao_admin(area_entry, quant_entry, min_entry, tree):
    """Salva la configuración del stock mínimo"""
    area = area_entry.get()
    try:
        quantidade = int(quant_entry.get())
        minimo = int(min_entry.get())
        if quantidade < 0 or minimo < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Erro", "Valores inválidos!")
        return
    
    if not area:
        messagebox.showerror("Erro", "Selecione uma área!")
        return
    
    # Atualizar estoque
    if current_model == "313":
        estoque_313[area]["quantidade"] = quantidade
        estoque_313[area]["minimo"] = minimo
    else:
        estoque_314[area]["quantidade"] = quantidade
        estoque_314[area]["minimo"] = minimo
    
    salvar_estoque()
    atualizar_tabela_estoque(tree, estoque)
    messagebox.showinfo("Sucesso", "Configuração salva com sucesso!")
    reset_inactivity_timer()

def voltar_tela_inicial():
    """Volta para a tela inicial de login"""
    global bloquear_leitura, ultimo_rfid_lido, ultimo_tempo_leitura, current_user, current_user_role, current_model
    
    # Resetar todas as variáveis de sessão
    current_user = None
    current_user_role = None
    current_model = None
    bloquear_leitura = False
    ultimo_rfid_lido = None
    ultimo_tempo_leitura = 0
    
    # Cancelar todos os callbacks pendentes
    cancel_pending_callbacks()
    
    # Limpar a interface
    for widget in root.winfo_children():
        widget.destroy()
    
    # Recriar a tela inicial
    setup_main_screen()
    
    # Reiniciar animação
    start_wave_animation()

# ---------------- FUNÇÕES DE ANIMAÇÃO E GUI ----------------

def draw_wave_animation():
    """Desenha a animação de onda"""
    global wave_offset, wave_animation_active
    
    if not wave_animation_active or not wave_canvas:
        if running:
            schedule_callback(100, draw_wave_animation)
        return
    
    wave_canvas.delete("all")
    width, height = 400, 100
    
    # Fundo gradiente
    for i in range(width):
        r = int(236 - (236 - 52) * i / width)
        g = int(240 - (240 - 152) * i / width)
        b = int(241 - (241 - 219) * i / width)
        color = f'#{r:02x}{g:02x}{b:02x}'
        wave_canvas.create_line(i, 0, i, height, fill=color)
    
    # Ondas animadas
    points1 = []
    points2 = []
    points3 = []
    for x in range(0, width, 5):
        y1 = height/2 + 15 * math.sin((x + wave_offset) * 0.05)
        y2 = height/2 + 10 * math.cos((x + wave_offset) * 0.08 + 0.5) + 8
        y3 = height/2 + 8 * math.sin((x + wave_offset) * 0.07 + 1.0) - 8
        points1.append(x)
        points1.append(y1)
        points2.append(x)
        points2.append(y2)
        points3.append(x)
        points3.append(y3)
    
    if len(points1) > 2:
        wave_canvas.create_line(points1, fill="#3498db", smooth=True, width=3)
        wave_canvas.create_line(points2, fill="#2980b9", smooth=True, width=2)
        wave_canvas.create_line(points3, fill="#1abc9c", smooth=True, width=2)
    
    wave_offset += 2
    if wave_animation_active and running:
        schedule_callback(30, draw_wave_animation)

def start_wave_animation():
    """Inicia a animação das ondas"""
    global wave_animation_active
    wave_animation_active = True
    draw_wave_animation()

def stop_wave_animation():
    """Para a animação das ondas"""
    global wave_animation_active
    wave_animation_active = False

def setup_main_screen():
    """Configura a tela inicial"""
    global status_label, wave_canvas
    
    # Frame principal
    main_frame = tk.Frame(root, bg='white')
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Título
    title_frame = tk.Frame(main_frame, bg='white')
    title_frame.pack(pady=(50, 20))
    
    tk.Label(title_frame, text="Sistema de Controle de Estoque", 
             font=("Arial", 20, "bold"), bg='white', fg='#2c3e50').pack()
    tk.Label(title_frame, text="Aproxime seu cartão RFID para iniciar", 
             font=("Arial", 12), bg='white', fg='#7f8c8d').pack(pady=(5, 0))
    
    # Canvas para animação
    wave_canvas = tk.Canvas(main_frame, width=400, height=100, bg='white', highlightthickness=0)
    wave_canvas.pack(pady=20)
    
    # Status
    status_frame = tk.Frame(main_frame, bg='white')
    status_frame.pack(pady=20)
    
    status_label = tk.Label(status_frame, text="RFID leitor iniciado", 
                           font=("Arial", 10), bg='white', fg='#34495e')
    status_label.pack()
    
    # Iniciar animação
    start_wave_animation()

# ---------------- FUNÇÕES DE SERIAL/RFID ----------------

def init_serial():
    """Inicializa a comunicação serial"""
    global ser
    try:
        ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=0.1)
        print(f"Conectado à porta serial {PORTA_SERIAL}")
        return True
    except serial.SerialException as e:
        print(f"Erro ao conectar na porta serial {PORTA_SERIAL}: {e}")
        return False

def read_serial():
    """Lê dados da porta serial de forma não-bloqueante"""
    global ultimo_rfid_lido, ultimo_tempo_leitura, bloquear_leitura
    
    if not ser or not ser.is_open:
        return None
    
    try:
        # Lê uma linha com timeout curto para evitar bloqueio
        data = ser.readline().decode('utf-8', errors='ignore').strip()
        
        # Filtra dados inválidos ou vazios
        if not data or len(data) < 8 or not all(c in '0123456789ABCDEF' for c in data):
            return None
            
        return data
        
    except serial.SerialException as e:
        print(f"Erro na leitura serial: {e}")
        return None
    except UnicodeDecodeError:
        return None

def process_rfid(rfid_data):
    """Processa o dado RFID lido"""
    global ultimo_rfid_lido, ultimo_tempo_leitura, bloquear_leitura
    
    # Verifica se está bloqueado ou se é leitura duplicada
    current_time = time.time()
    if (bloquear_leitura or 
        (ultimo_rfid_lido == rfid_data and current_time - ultimo_tempo_leitura < 2)):
        return
    
    ultimo_rfid_lido = rfid_data
    ultimo_tempo_leitura = current_time
    
    print(f"Cartão lido: {rfid_data}")
    
    # Atualiza a interface na thread principal
    root.after(0, lambda: update_status(f"Cartão lido: {rfid_data}"))
    
    # Verifica se é um operador
    if rfid_data in operadores:
        nome = operadores[rfid_data]
        root.after(0, lambda: mostrar_selecao_modelo(nome, "operador"))
        return
    
    # Verifica se é um administrador
    if rfid_data in administradores:
        nome = administradores[rfid_data]
        root.after(0, lambda: mostrar_selecao_modelo(nome, "admin"))
        return
    
    # Cartão não reconhecido
    root.after(0, lambda: update_status(f"Cartão não reconhecido: {rfid_data}"))

def update_status(message):
    """Atualiza o status na interface"""
    if status_label:
        status_label.config(text=message)

def serial_thread_function():
    """Thread para leitura contínua da serial"""
    global running
    
    print("Thread serial iniciada")
    
    while running:
        try:
            if not ser or not ser.is_open:
                time.sleep(1)
                continue
                
            # Lê dados da serial
            rfid_data = read_serial()
            
            if rfid_data:
                process_rfid(rfid_data)
                
            # Pequena pausa para não sobrecarregar a CPU
            time.sleep(0.05)
            
        except Exception as e:
            print(f"Erro na thread serial: {e}")
            time.sleep(1)

# ---------------- INICIALIZAÇÃO E FINALIZAÇÃO ----------------

def cleanup():
    """Limpeza ao finalizar o programa"""
    global running, ser
    
    print("Finalizando programa...")
    running = False
    
    # Fechar porta serial
    if ser and ser.is_open:
        ser.close()
        print("Porta serial fechada")
    
    # Salvar estoque
    salvar_estoque()
    print("Estoque salvo")

def main():
    """Função principal"""
    global ser, serial_thread, running
    
    # Carregar estoque
    carregar_estoque()
    
    # Inicializar serial
    if not init_serial():
        messagebox.showerror("Erro", f"Não foi possível conectar na porta serial {PORTA_SERIAL}")
        return
    
    # Configurar interface
    setup_main_screen()
    
    # Iniciar thread serial
    serial_thread = threading.Thread(target=serial_thread_function, daemon=True)
    serial_thread.start()
    
    print("Sistema iniciado. Aguardando cartões RFID...")
    
    # Registrar cleanup
    atexit.register(cleanup)
    
    # Iniciar loop principal
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Interrompido pelo usuário")
    finally:
        running = False
        if serial_thread and serial_thread.is_alive():
            serial_thread.join(timeout=1.0)
        cleanup()

# ---------------- EXECUÇÃO ----------------
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Sistema de Controle de Estoque - RFID")
    root.geometry("800x600")
    root.configure(bg='white')
    
    # Centralizar janela
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Iniciar aplicação
    main()
