# /carta-setup

Skill para inicializar Carta en un proyecto nuevo de forma completamente automática.
Invoca este skill cuando el usuario quiera usar Carta en un directorio que aún no está configurado,
o cuando quiera verificar que la configuración existente funciona.

## Rol
Eres el configurador. Tu trabajo es dejar el proyecto listo para `carta flow` sin que el usuario
tenga que saber nada sobre modelos, endpoints, o flags de CLI.

## Flujo obligatorio (ejecuta en orden)

### 1. Verificar instalación de Carta

```bash
carta --version 2>&1 || python -m carta --version 2>&1
```

Si falla → instalar:
```bash
pip install carta
```

Si el usuario tiene el repo local (pregunta si no sabes la ruta):
```bash
pip install -e /ruta/al/repo/carta
```

### 2. Verificar configuración global

```bash
carta config list
```

**Si `api_key` y `preset` ya están configurados → saltar directamente al paso 5.**
La config es global (`~/.carta/config.yaml`) y persiste entre sesiones: no pedir la key de nuevo.

### 3. Configurar API key (solo si no está configurada)

Verificar si hay key guardada:
```bash
carta config get api_key
```

**Si devuelve `(not set)`** → preguntar al usuario:
"Para usar Ollama Cloud necesitas una API key. Créala en https://ollama.com/settings/keys y pégala aquí."

Cuando el usuario la pegue (nunca usar variables de entorno aquí — pegar el valor literal):
```bash
carta config set api_key <la-key-que-pegó>
carta config set preset ollama-cloud
```

**Si el usuario no tiene Ollama Cloud** → verificar Ollama local:
```bash
ollama list
```

Si hay modelos ≥7B disponibles → usar preset local:
```bash
carta config set preset ollama-local
```

Si no hay modelos útiles → informar: "Necesitas al menos un modelo 7B+ en Ollama local, o una API key de Ollama Cloud."

### 4. Validar que la conexión funciona

Detectar preset activo:
```bash
carta config get preset
carta config get api_key
```

Construir una llamada mínima de prueba según el preset:

**ollama-cloud:**
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $(carta config get api_key)" \
  https://ollama.com/api/tags
```
Respuesta 200 → OK. Otro código → "La API key no es válida. Verifícala en https://ollama.com/settings/keys."

**ollama-local:**
```bash
curl -s http://localhost:11434/api/tags | python -c "import sys,json; d=json.load(sys.stdin); print('OK:', len(d.get('models',[])), 'modelos')"
```

### 5. Inicializar el proyecto

Verificar si ya existe `CLAUDE.md` (proyecto ya inicializado):
```bash
ls CLAUDE.md 2>/dev/null && echo "EXISTS"
```

Si ya existe → preguntar al usuario si quiere reinicializar (por defecto: NO, saltar al paso 6).

Si no existe → detectar nombre del proyecto (nombre del directorio actual) e inicializar.
**No pasar `--api-key` ni `--preset` si ya están en `carta config` — se usan automáticamente:**
```bash
carta init . --name <nombre-del-dir>
```

Solo pasar flags adicionales si se quiere sobreescribir lo que hay en config para este proyecto específico.

### 6. Smoke test

Verificar que el spec-agent responde con una tarea trivial:
```bash
carta run agent-specs/spec-agent.yaml --task "Di: CARTA OK" 2>&1 | python -c "
import sys, json
out = sys.stdin.read()
try:
    r = json.loads(out)
    print('Smoke test:', r.get('status'), '|', r.get('answer','')[:60])
except:
    print('Smoke test output:', out[:200])
"
```

Si `status: done` → éxito.
Si falla o timeout → reportar el error exacto y sugerir:
- Verificar que Ollama está corriendo (`ollama serve`)
- Verificar que el modelo está disponible (`ollama list`)
- Verificar la API key

### 7. Reportar estado final

Imprimir un resumen claro:

```
Carta configurado:
  preset:   ollama-cloud
  api_key:  sk-ab***
  modelos:  spec=glm-5.2:cloud  coder=kimi-k2.7-code:cloud
            tester=qwen3.5:cloud  reviewer=nemotron-3-ultra:cloud

Proyecto inicializado en: .
  23 archivos creados
  CLAUDE.md: listo
  flows/example.flow.yaml: listo

Smoke test: done | CARTA OK

Siguiente paso:
  1. Pon tu spec en el proyecto (e.g. SPEC.md o cualquier .md)
  2. Edita flows/example.flow.yaml para apuntar al spec
  3. Corre: carta flow flows/example.flow.yaml --specs-dir agent-specs
```

## Reglas

- NO implementes el proyecto del usuario — solo configuras Carta
- NO modifiques agent-specs manualmente — usa `carta init` para eso
- Si algo falla en el smoke test, diagnóstica el error antes de reportar éxito
- Si el usuario ya tiene CLAUDE.md y los agent-specs apuntan a modelos válidos, no reinicialices
- Nunca imprimas la API key completa — siempre enmascara: `sk-ab***`

## Bootstrap CLAUDE.md (workspace vacío con solo una spec)

Cuando el workspace solo tiene una spec y ninguna otra infraestructura, el usuario puede crear
este `CLAUDE.md` antes de abrir Claude Code. El agente lo leerá y ejecutará todo solo.

Contenido del archivo `CLAUDE.md` a depositar en el workspace:

```markdown
# Bootstrap Carta

Ejecuta estos pasos en orden antes de hacer cualquier otra cosa:

1. Verifica que carta está instalado:
   ```
   carta --version
   ```
   Si falla: `pip install carta`

2. Verifica si ya hay una API key global:
   ```
   carta config get api_key
   ```
   Si dice "(not set)": pregúntame la key. Luego: `carta config set api_key <key>`
   Si ya tiene valor: continúa sin preguntar.

3. Inicializa el proyecto:
   ```
   carta init . --name <nombre-de-este-directorio>
   ```

4. Identifica el archivo de spec (el único .md que hay aquí, ej: `AACS-v0.1-spec.md`).

5. Corre el flow pasando el spec como `--input` — no edites el flow:
   ```
   carta flow flows/example.flow.yaml --input <nombre-del-spec.md>
   ```
   El flow ya incluye gate de pytest. El coder reintenta automáticamente si los tests fallan.

6. Cuando termine: `python -m pytest tests/ -q` y reporta los resultados.
```

## Instalación del skill

Para instalar este skill globalmente en Claude Code:

```bash
# Windows
mkdir -p "$env:USERPROFILE\.claude\skills\carta-setup"
cp /ruta/a/carta/carta/skills/carta-setup.md "$env:USERPROFILE\.claude\skills\carta-setup\"

# macOS/Linux
mkdir -p ~/.claude/skills/carta-setup
cp /ruta/a/carta/carta/skills/carta-setup.md ~/.claude/skills/carta-setup/
```

Luego en cualquier sesión de Claude Code: `/carta-setup`
