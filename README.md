# Protocolos de investigación · Centro de Ojos Loria

Aplicación web privada para llevar los protocolos de investigación del sitio:
la coordinadora carga **quién hizo cada procedimiento** en cada visita y el
sistema calcula solo lo demás: lo que le corresponde a cada médico, lo que hay
que cobrarle al sponsor, lo que está facturado y cobrado, y el reparto.

Primer protocolo cargado: **MALBEC (MK-8748-002)**, con su historial hasta el 18/11/2026.

## Roles

- **Coordinadora de estudios**: pacientes (solo el código de sujeto), visitas y
  quién hizo cada procedimiento. **No ve ningún importe** ni entra a las
  pantallas de dinero (verificado en el servidor: `estudios/tests.py`).
- **Dirección**: todo. Tablero, médicos, cobros al sponsor, reparto y Configuración.

Los usuarios se crean en Configuración → Usuarios. Nacen con una clave genérica
y el sistema obliga a cambiarla en el primer ingreso.

## Cómo calcula

- **Médicos**: cada procedimiento cargado toma la tarifa del protocolo
  (Configuración → Protocolos). Saldo = lo que le corresponde − lo pagado.
  A quien **deriva** un paciente se le suman USD 1.000 (configurable por
  protocolo) cuando el paciente entra al estudio (Day 1).
  Los pagos se guardan en USD y, si se paga en pesos, con el dólar BNA vendedor del día.
- **Cobros al sponsor**: cada visita completa vale el precio del presupuesto;
  aparte van el viático por visita y los condicionales (OCTA, FAF). Una visita
  está *sin facturar* hasta que entra en una factura, y *cobrada* cuando la
  factura se marca cobrada. Las cartas de pago trimestrales (payment letters)
  se cargan en Configuración.
- **Carta de pago**: en Cobros → “Subir carta de pago” se sube el PDF de la
  CRO. El sistema lee el Request ID, la fecha y cada visita, las compara con lo
  cargado (coincide, ya facturada, importe distinto, no cargada), avisa qué
  visitas del trimestre quedaron afuera y genera las facturas de visitas y de
  viáticos con el Request ID correcto.
- **Factura en PDF**: cada factura se descarga lista para mandar. Los datos
  del sitio, de la CRO y del banco se completan una vez por protocolo en
  Configuración → Protocolos (el CUIT y la cuenta no están en el código).
- **Cotización**: al registrar un pago se trae el dólar vendedor (billete) del
  Banco Nación de bna.com.ar; si no responde, se escribe a mano.
- **Reparto** (regla fija para todos los estudios, sobre lo cobrado):
  neto = cobrado − gastos − pagos a médicos; del neto sale primero el 10% de
  quien trae el estudio y el resto se divide 50 / 40 / 10. A cada uno se le
  devuelve lo que adelantó. Los porcentajes están en Configuración → Socios.
- **Avisos**: visitas del cronograma sin cargar, facturas vencidas y facturas
  con un Request ID distinto al de su carta.

## Sumar otro protocolo

“+ Protocolo” en el menú: se sube el presupuesto del sitio (el Excel de la CRO
con una columna por visita). El sistema calcula el precio de cada visita con
el overhead, el viático y los condicionales, propone los procedimientos de
cada visita y muestra todo para revisar antes de crear. Las tarifas de los
médicos se copian de un protocolo existente y se ajustan en Configuración.
Con más de un protocolo activo aparece un selector en el encabezado.

## Correr en desarrollo

```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py datos_iniciales   # MALBEC + usuario jvalenzuela (clave genérica)
python manage.py runserver
python manage.py test
```

## Despliegue en Render

1. En render.com: New → Blueprint → elegir este repositorio (usa `render.yaml`).
2. El build corre las migraciones y `datos_iniciales`, que carga MALBEC y el
   usuario inicial **solo si la base está vacía** (nunca pisa datos).
3. Si el nombre del servicio cambia, ajustar `DJANGO_ALLOWED_HOSTS`.

Misma base técnica que la app de presupuestos: Django, PostgreSQL en Render,
bloqueo de cuenta tras 5 intentos fallidos, HTTPS forzado y secretos por
variables de entorno.
