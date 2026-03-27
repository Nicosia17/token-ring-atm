import socket
import threading
import sys
import time
import os
import queue
from datetime import datetime
from config import (NODES, INITIAL_BALANCE, BALANCE_FILE,
                    RETRY_DELAY, MAX_RETRIES, TOKEN_PAUSE, SILENT_MODE)

# Lock globale per evitare output interlacciati tra thread.
log_lock = threading.Lock()

def log(my_id, message):
    # Log tecnico: serve per tracciare token, transazioni e debug.
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}][ATM{my_id}] {message}"
    with open(f"atm{my_id}.log", "a") as f:
        f.write(line + "\n")
    if not SILENT_MODE:
        with log_lock:
            print(line)

def notify(my_id, message):
    # Log utente: va sempre a terminale + file.
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}][ATM{my_id}] {message}"
    with log_lock:
        print(line)
    with open(f"atm{my_id}.log", "a") as f:
        f.write(line + "\n")

def init_balance(my_id):
    # Il saldo è condiviso via file: ATM1 lo crea se non esiste.
    if not os.path.exists(BALANCE_FILE):
        with open(BALANCE_FILE, "w") as f:
            f.write(str(INITIAL_BALANCE))
        notify(my_id, f"💳 Saldo iniziale creato: {INITIAL_BALANCE}€")

def read_balance():
    # Lettura del saldo corrente dal file condiviso.
    with open(BALANCE_FILE, "r") as f:
        return int(f.read().strip())

def write_balance(amount):
    # Scrittura atomica del nuovo saldo sul file condiviso.
    with open(BALANCE_FILE, "w") as f:
        f.write(str(amount))

def show_history(my_id):
    # Ricostruisce lo storico leggendo il log dell'ATM locale.
    log_file = f"atm{my_id}.log"
    if not os.path.exists(log_file):
        notify(my_id, "Nessun log disponibile ancora.")
        return
    with open(log_file, "r") as f:
        lines = f.readlines()
    # Ogni transazione è un blocco tra INIZIO/FINE TRANSAZIONE.
    transazioni = []
    blocco_corrente = None
    for line in lines:
        line = line.strip()
        # Individuo l'inizio di un nuovo blocco transazione.
        if "INIZIO TRANSAZIONE" in line:
            try:
                tx_id = line.split("INIZIO TRANSAZIONE")[1].strip().replace("══", "").strip()
            except:
                tx_id = "TX-???"
            blocco_corrente = {"id": tx_id, "atm": f"ATM{my_id}", "lines": []}
        # Quando arrivo alla fine, salvo il blocco.
        elif "FINE TRANSAZIONE" in line and blocco_corrente is not None:
            transazioni.append(blocco_corrente)
            blocco_corrente = None
        # Raccatto solo le righe interessanti per il riepilogo.
        elif blocco_corrente is not None:
            keywords = ["ATM", "Operazione", "Saldo prima", "Saldo dopo", "insufficiente"]
            if any(k in line for k in keywords):
                try:
                    content = line.split("]", 2)[-1].strip()
                except:
                    content = line
                blocco_corrente["lines"].append(content)
    # Passaggi del token senza operazioni: utili per capire il flusso.
    passaggi_vuoti = [l.strip() for l in lines if "Nessuna operazione in coda" in l]
    with log_lock:
        print(f"\n  ╔══════════════════════════════════════════════╗")
        print(f"  ║        ATM{my_id} — Storico Movimenti              ║")
        print(f"  ╚══════════════════════════════════════════════╝")
        if not transazioni:
            print(f"  Nessuna transazione eseguita ancora su ATM{my_id}.")
        else:
            for tx in transazioni:
                print(f"\n  ┌─ {tx['id']} — {tx['atm']} {'─' * 28}")
                for detail in tx["lines"]:
                    print(f"  │  {detail}")
                print(f"  └{'─' * 45}")
        print(f"\n  📋 Riepilogo:")
        print(f"     • Transazioni completate : {len(transazioni)}")
        print(f"     • Passaggi senza azione  : {len(passaggi_vuoti)}")
        print(f"     • Token ricevuti totali  : {len(transazioni) + len(passaggi_vuoti)}")
        print(f"\n  ╔══════════════════════════════════════════════╗")
        print(f"  ║Saldo attuale: {read_balance()}€{' ' * (30 - len(str(read_balance())))} ║")
        print(f"  ╚══════════════════════════════════════════════╝")

pending_operations = queue.Queue()
# Event usato per bloccare il menu quando il token è in esecuzione.
token_busy = threading.Event()

tx_counter = 0
# Lock per incrementare il contatore transazioni in modo sicuro.
tx_lock = threading.Lock()

def execute_transaction(my_id):
    """
    Esegue una transazione bancaria SOLO se questo nodo possiede il token.

    MUTUA ESCLUSIONE GARANTITA:
    Questa funzione è chiamata ESCLUSIVAMENTE dal branch TOKEN in
    handle_message(). Non esiste nessun altro percorso che acceda
    a balance.txt → la mutua esclusione è strutturale.

    ATOMICITÀ:
    read → validate → compute → write avvengono in sequenza sincrona.
    Nessun interleaving con altri nodi (il token è unico nel sistema).

    RISORSA CONDIVISA — balance.txt:
    Tutti e 4 i nodi leggono/scrivono lo stesso file su disco.
    Nessuna variabile globale in memoria è condivisa tra i processi.
    """
    global tx_counter
    # Sezione critica: viene eseguita solo quando il nodo possiede il token.
    # La mutua esclusione è garantita perché il token è unico nel sistema.
    if pending_operations.empty():
        # Nessuna operazione → il token viene inoltrato immediatamente
        log(my_id, "Nessuna operazione in coda → passo il token.")
        return
    # Prelevo l'operazione accodata (FIFO).
    operation, amount = pending_operations.get()
    with tx_lock:
        tx_counter += 1
        tx_id = f"TX-{tx_counter:03d}"
    # Step 1: lettura dal file condiviso
    balance = read_balance()
    # Transazione atomica: lettura → validazione → aggiornamento → scrittura → log.
    log(my_id, f"══ INIZIO TRANSAZIONE {tx_id} ══")
    log(my_id, f"ID          : {tx_id}")
    log(my_id, f"ATM         : ATM{my_id}")
    log(my_id, f"Operazione  : {operation.upper()} di {amount}€")
    log(my_id, f"Saldo prima : {balance}€")
    # Step 2: validazione
    if operation == "prelievo" and amount > balance:
        notify(my_id, f"❌ Saldo insufficiente ({balance}€). Annullata.")
        log(my_id, f"══ FINE TRANSAZIONE {tx_id} ══")
        return

    # Step 3: aggiornamento
    if operation == "prelievo":
        new_balance = balance - amount
    elif operation == "deposito":
        new_balance = balance + amount
    else:
        log(my_id, f"Operazione sconosciuta: {operation}. Annullata.")
        return
    # Step 4: scrittura sul file condiviso
    # Il token viene passato DOPO questo punto → nessun altro nodo
    # può leggere un saldo intermedio o inconsistente.
    write_balance(new_balance)
    log(my_id, f"Saldo dopo  : {new_balance}€")
    log(my_id, f"══ FINE TRANSAZIONE {tx_id} ══")
    notify(my_id, f"✅ [{tx_id}] {operation.upper()} di {amount}€ su ATM{my_id} completato! Nuovo saldo: {new_balance}€")

running = True
# Set usato da ATM1 per sapere quando tutti i nodi sono operativi.
ready_nodes = set()
ready_lock = threading.Lock()
# Event che sblocca i menu quando il sistema è pronto.
all_ready_event = threading.Event()

def get_successor_id(my_id):
    # Successore nell'anello logico (1→2→3→4→1).
    return (my_id % 4) + 1

def send_message(my_id, target_id, message):
    """
    Invia un messaggio TCP al nodo target_id.

    Topologia anello logico:
      ATM1 (5001) → ATM2 (5002) → ATM3 (5003) → ATM4 (5004) → ATM1

    Formato messaggi:
      TOKEN:<round>  — il token con numero di round
      READY:<id>     — segnale di disponibilità ad ATM1
      STOP           — comando di arresto propagato nell'anello

    Connessione TCP short-lived: una connessione per ogni messaggio.
    Meccanismo di retry: MAX_RETRIES tentativi con RETRY_DELAY di attesa.
    """
    host, port = NODES[target_id]
    for attempt in range(MAX_RETRIES):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)           # timeout 3s
                s.connect((host, port))   # TCP verso target_id
                s.sendall(message.encode())
            log(my_id, f">> Inviato ad ATM{target_id}: '{message}'")
            return True
        except (ConnectionRefusedError, socket.timeout):
            if attempt < MAX_RETRIES - 1:
                log(my_id, f"ATM{target_id} non risponde, riprovo ({attempt+1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)   # attesa tra un tentativo e l'altro
    log(my_id, f"Impossibile raggiungere ATM{target_id} dopo {MAX_RETRIES} tentativi.")
    return False

def handle_message(my_id, message):
    global running
    # Dispatcher centrale per tutti i messaggi TCP in arrivo.
    # Tre tipi di messaggio:
    #   - READY:<id>    → nodo secondario segnala disponibilità ad ATM1
    #   - TOKEN:<round> → questo nodo riceve il token (SEZIONE CRITICA)
    #   - STOP          → arresto ordinato propagato nell'anello

    if message.startswith("READY"):
        # READY serve ad ATM1 per sapere che tutti i nodi sono online.
        _, sender_id = message.split(":")
        sender_id = int(sender_id)
        with ready_lock:
            ready_nodes.add(sender_id)
            log(my_id, f"ATM{sender_id} è pronto ({len(ready_nodes)}/3)")
            if ready_nodes == {2, 3, 4}:
                log(my_id, "Tutti e 4 i nodi sono pronti!")
                all_ready_event.set()
    elif message.startswith("TOKEN"):
        _, round_num = message.split(":")
        round_num = int(round_num)
        # Gestione del token: quando arriva, entro in sezione critica
        # e poi lo inoltro al successore per mantenere l’anello attivo.
        if not all_ready_event.is_set():
            all_ready_event.set()
        # ── INIZIO SEZIONE CRITICA ─────────────────────────────
        # Questo nodo è ora l'UNICO proprietario del token.
        # Può accedere in modo esclusivo a balance.txt.
        # Nessun altro nodo può eseguire transazioni ora.
        # Blocco l'interfaccia mentre il token è in uso.
        token_busy.set()
        log(my_id, f"★ TOKEN RICEVUTO — round {round_num}")
        notify(my_id, f"🔄 Token ricevuto (round {round_num})")
        if not pending_operations.empty():
            notify(my_id, "🔑 Token ricevuto — eseguo la tua operazione...")
        # Sezione critica: eseguo al massimo una transazione per passaggio.
        execute_transaction(my_id)
        successor = get_successor_id(my_id)
        # Il round incrementa solo quando il token completa
        # un giro completo (quando lascia ATM4 verso ATM1)
        next_round = round_num + 1 if my_id == 4 else round_num
        # Piccola pausa per rendere visibile il passaggio del token.
        time.sleep(TOKEN_PAUSE)
        log(my_id, f">> Passo il token ad ATM{successor} (round {next_round})")
        token_busy.clear()
        notify(my_id, f"➡️ Token inoltrato ad ATM{successor} (round {next_round})")
        # ── FINE SEZIONE CRITICA ───────────────────────────────
        # Inoltro token al successore → anello continua
        send_message(my_id, successor, f"TOKEN:{next_round}")
    elif message == "STOP":
        # STOP viene propagato per fermare tutti i nodi.
        log(my_id, "STOP ricevuto — il sistema si ferma.")
        notify(my_id, "🛑 Sistema fermato.")
        running = False
        token_busy.clear()
        successor = get_successor_id(my_id)
        if my_id != 1:
            send_message(my_id, successor, "STOP")

def user_menu(my_id, ready_event):
    # Il menu si attiva solo quando il sistema è operativo.
    ready_event.wait()
    time.sleep(1.0)
    notify(my_id, "✅ Sistema pronto! Puoi operare.")
    while running:
        # Se il token è in uso, evito input concorrenti.
        while token_busy.is_set():
            time.sleep(0.1)
        with log_lock:
            print(f"\n  ╔══════════════════════════════════╗")
            print(f"  ║         ATM{my_id} — Menu              ║")
            print(f"  ╠══════════════════════════════════╣")
            print(f"  ║  1. Visualizza saldo             ║")
            print(f"  ║  2. Deposita                     ║")
            print(f"  ║  3. Preleva                      ║")
            print(f"  ║  4. Storico movimenti            ║")
            print(f"  ║  5. Esci                         ║")
            print(f"  ╚══════════════════════════════════╝")
        try:
            scelta = input(f"[ATM{my_id}] Scelta: ").strip()
        except EOFError:
            break
        if scelta == "1":
            # Lettura saldo: non modifica la risorsa condivisa.
            balance = read_balance()
            notify(my_id, f"💰 Saldo attuale: {balance}€")
        elif scelta == "2":
            try:
                amount = int(input(f"[ATM{my_id}] Importo da depositare (€): ").strip())
                if amount <= 0:
                    notify(my_id, "❌ Importo non valido.")
                    continue
                # Accodo l'operazione: verrà eseguita al prossimo token.
                pending_operations.put(("deposito", amount))
                notify(my_id, f"⏳ Deposito {amount}€ accodato — verrà eseguito al prossimo token.")
            except ValueError:
                notify(my_id, "❌ Inserisci un numero intero valido.")
        elif scelta == "3":
            try:
                amount = int(input(f"[ATM{my_id}] Importo da prelevare (€): ").strip())
                if amount <= 0:
                    notify(my_id, "❌ Importo non valido.")
                    continue
                # Accodo l'operazione: verrà eseguita al prossimo token.
                pending_operations.put(("prelievo", amount))
                notify(my_id, f"⏳ Prelievo {amount}€ accodato — verrà eseguito al prossimo token.")
            except ValueError:
                notify(my_id, "❌ Inserisci un numero intero valido.")
        elif scelta == "4":
            show_history(my_id)
        elif scelta == "5":
            notify(my_id, "👋 Uscita.")
            os._exit(0)
        else:
            notify(my_id, "❌ Scelta non valida.")

def start_server(my_id):
    # Server TCP locale che riceve READY/TOKEN/STOP.
    host, port = NODES[my_id]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)
        log(my_id, f"Server avviato sulla porta {port}")
        while running:
            server.settimeout(1.0)
            try:
                conn, addr = server.accept()
                with conn:
                    data = conn.recv(1024).decode().strip()
                    if data:
                        threading.Thread(
                            target=handle_message,
                            args=(my_id, data),
                            daemon=True
                        ).start()
            except socket.timeout:
                continue

def send_ready(my_id):
    # ATM2/3/4 avvisano ATM1 di essere online.
    host, port = NODES[1]
    for attempt in range(MAX_RETRIES):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((host, port))
                s.sendall(f"READY:{my_id}".encode())
            log(my_id, "READY inviato ad ATM1")
            return True
        except (ConnectionRefusedError, socket.timeout):
            log(my_id, f"ATM1 non ancora pronto, riprovo... ({attempt+1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
    log(my_id, "Impossibile contattare ATM1.")
    return False

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["1", "2", "3", "4"]:
        print("Uso: python atm.py <ID>   dove ID è 1, 2, 3 o 4")
        sys.exit(1)
    my_id = int(sys.argv[1])
    successor_id = get_successor_id(my_id)
    # Pulizia del log per una sessione ordinata.
    with open(f"atm{my_id}.log", "w") as f:
        f.write(f"=== Sessione ATM{my_id} — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ===\n")
    print(f"\n╔══════════════════════════════════════╗")
    print(f"  ATM{my_id} avviato | Successore: ATM{successor_id}")
    print(f"╚══════════════════════════════════════╝\n")
    if my_id == 1:
        # Solo ATM1 inizializza il saldo.
        init_balance(my_id)
    threading.Thread(target=start_server, args=(my_id,), daemon=True).start()
    if my_id != 1:
        # ATM2/3/4 inviano READY e poi attendono il primo TOKEN.
        time.sleep(0.5)
        def ready_and_wait():
            ok = send_ready(my_id)
            if not ok:
                log(my_id, "Non ho raggiunto ATM1 — aspetto il primo token per sbloccarmi.")
        threading.Thread(target=ready_and_wait, daemon=True).start()
    else:
        # ATM1 aspetta tutti i READY e poi immette il token nell'anello.
        notify(my_id, "⏳ Aspetto che ATM2, ATM3 e ATM4 siano pronti...")
        all_ready_event.wait()
        time.sleep(0.3)
        notify(my_id, "🚀 Lancio il token nell'anello!")
        send_message(my_id, successor_id, "TOKEN:1")
    threading.Thread(
        target=user_menu,
        args=(my_id, all_ready_event),
        daemon=True
    ).start()
    while running:
        time.sleep(0.5)
    log(my_id, "Sistema terminato.")
