# Token Ring ATM (4 nodi)

Questo progetto simula 4 ATM su localhost con mutua esclusione tramite Token Ring.
Ogni nodo è un processo separato e comunica via TCP. Il saldo è condiviso via file
`balance.txt` e viene modificato **solo** dal nodo che possiede il token.

## Avvio rapido

Apri **4 terminali** nella cartella del progetto ed esegui:

```bash
/usr/bin/python3 atm.py 1
/usr/bin/python3 atm.py 2
/usr/bin/python3 atm.py 3
/usr/bin/python3 atm.py 4
```

## Sequenza richiesta (manuale)

1. **ATM1**: possiede il token, nessuna transazione, inoltra il token (saldo 1000)
2. **ATM2**: prelievo 200 → saldo 800
3. **ATM3**: deposito 100 → saldo 900
4. **ATM4**: prelievo 500 → saldo 400

### Checklist pratica (4 terminali)

- Avvia i 4 nodi in terminali separati.
- Su **ATM2** accoda un **prelievo 200**.
- Su **ATM3** accoda un **deposito 100**.
- Su **ATM4** accoda un **prelievo 500**.
- Attendi il passaggio del token: le operazioni verranno eseguite in ordine.
- Verifica i log (`atm2.log`, `atm3.log`, `atm4.log`) e il saldo finale in `balance.txt`.

## Logging richiesto

Ogni nodo registra:
- ricezione del token
- inoltro del token
- inizio transazione
- fine transazione
- saldo aggiornato

I log sono in `atm1.log`, `atm2.log`, `atm3.log`, `atm4.log`.

### Dove si vede nei log

- **Token ricevuto**: riga con `TOKEN RICEVUTO`
- **Token inoltrato**: riga con `Passo il token`
- **Inizio/Fine transazione**: `INIZIO TRANSAZIONE` / `FINE TRANSAZIONE`
- **Saldo aggiornato**: `Saldo dopo`

## Note

- L’ordine delle operazioni è garantito dal token.
- Non esiste memoria condivisa tra processi: il file del saldo è l’unica risorsa comune.
