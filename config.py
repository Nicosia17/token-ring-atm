HOST = "localhost"

# Porte fisse per ogni ATM
NODES = {
    1: (HOST, 5001),
    2: (HOST, 5002),
    3: (HOST, 5003),
    4: (HOST, 5004),
}

INITIAL_BALANCE = 1000          # saldo iniziale del conto condiviso
BALANCE_FILE    = "balance.txt" # file usato come risorsa condivisa tra processi
RETRY_DELAY     = 0.5           # secondi tra un tentativo e l'altro di connessione
MAX_RETRIES     = 5            # tentativi massimi prima di arrendersi
TOKEN_PAUSE     = 3.0           # pausa tra un passaggio del token e l'altro
SILENT_MODE     = True
