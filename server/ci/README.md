# Plantilla de GitHub Actions

`server-workflow.yml.example` comprueba las funciones de Node-RED con Node.js 16/24 y el contrato de Grafana con Python 3.12. Es una plantilla **sin activar**.

La autorización disponible durante la publicación permitió subir código y documentación, pero rechazó archivos bajo `.github/workflows` por falta del permiso OAuth `workflow`. Las pruebas locales y de lectura contra el servidor sí se ejecutaron y están documentadas; no equivalen a un run de Actions.

Para activarla más adelante, un mantenedor con permiso de workflows puede revisarla y copiarla a `.github/workflows/server.yml`. No necesita secretos ni acceso a la infraestructura doméstica.
