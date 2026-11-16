# Sicurezza

## Segnalare una vulnerabilità

Per segnalare un problema di sicurezza usa la funzione
[Report a vulnerability](https://github.com/gcblack1984/APPhash/security/advisories/new)
di GitHub, che resta riservata fino alla correzione. Per i problemi non riservati apri una
normale [issue](https://github.com/gcblack1984/APPhash/issues).

## Versioni supportate

Viene mantenuta solo l'ultima versione pubblicata.

## Verificare un download

Ogni release contiene `SHA256SUMS.txt`. In PowerShell:

```powershell
Get-FileHash .\APPhash-vX.Y.Z-windows-x64.zip -Algorithm SHA256
```

Il valore deve coincidere con quello riportato nel file.
