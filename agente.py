import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.adk.agents import Agent


# Carga las credenciales del archivo .env (está en esta misma carpeta)
load_dotenv(Path(__file__).parent / ".env")

# Lee los valores del .env
proveedor = os.getenv("PROVEEDOR", "gemini")  # gemini, openai u ollama

# Gemini lee la clave GEMINI_API_KEY que cargó load_dotenv
modelo = "gemini-flash-lite-latest"

# Carpeta donde están los archivos CSV (junto a este archivo)
carpeta = Path(__file__).parent / "datos"


# Funciones auxiliares (no son herramientas del agente)
def _siguiente_id(df: pd.DataFrame, columna: str) -> int:
    """Devuelve el siguiente id disponible (1 si la tabla está vacía)."""
    return int(df[columna].max()) + 1 if not df.empty else 1

def _guardar(df: pd.DataFrame, archivo: str) -> None:
    """Guarda el CSV con BOM para que Excel muestre bien las tildes."""
    df.to_csv(carpeta / archivo, index=False, encoding="utf-8-sig")

def _validar_meses(mes_inicio: str, mes_fin: str) -> str | None:
    """Devuelve un mensaje de error si los meses no son válidos, o None si están bien."""
    for mes in (mes_inicio, mes_fin):
        if mes:
            try:
                pd.to_datetime(mes, format="%Y-%m")
            except (ValueError, TypeError):
                return f"Mes inválido: {mes}. Debe tener el formato AAAA-MM, por ejemplo 2026-03"
    if mes_inicio and mes_fin and mes_inicio > mes_fin:
        return "El mes de inicio no puede ser posterior al mes de fin"
    return None

def _pagos_del_periodo(mes_inicio: str, mes_fin: str) -> pd.DataFrame:
    """Lee los pagos, agrega la columna 'mes' (AAAA-MM) y filtra por periodo."""
    pago = pd.read_csv(carpeta / "pago.csv")
    pago["fecha_pago"] = pd.to_datetime(pago["fecha_pago"])
    pago["mes"] = pago["fecha_pago"].dt.strftime("%Y-%m")
    if mes_inicio:
        pago = pago[pago["mes"] >= mes_inicio]
    if mes_fin:
        pago = pago[pago["mes"] <= mes_fin]
    return pago

def _buscar_idioma(idioma: str, docente: pd.DataFrame) -> str | None:
    """Devuelve el idioma tal como está en la base de datos (sin importar
    mayúsculas ni espacios), o None si no existe."""
    validos = {str(i).strip().lower(): i for i in docente["idioma"].dropna().unique()}
    return validos.get(idioma.strip().lower())


# Funciones que usara el agente
def matriculas_totales() -> dict:
    """Devuelve el total de matrículas"""
    matriculas = pd.read_csv(carpeta / "matricula.csv")
    return {
        "cantidad": int(len(matriculas)),
    }

def registrar_alumno(nombre: str, genero: str, edad: int) -> dict:
    """Necesita nombre, genero y edad del estudiante que se registrara
       en caso de no proporcionar alguna de las 3 informaciones requeridas
       se debe solicitar nuevamente los datos faltantes """
    if not nombre or not genero or edad is None:
        return {"error": "Faltan datos: se requiere nombre, género y edad"}
    if int(edad) <= 0:
        return {"error": "La edad debe ser mayor que 0"}
    estudiante = pd.read_csv(carpeta / "estudiante.csv")
    nuevo_estudiante = {
        "id_estudiante": _siguiente_id(estudiante, "id_estudiante"),
        "nombre": nombre.strip(),
        "edad": int(edad),
        "genero": genero.strip(),
    }
    estudiante = pd.concat([estudiante, pd.DataFrame([nuevo_estudiante])], ignore_index=True)
    _guardar(estudiante, "estudiante.csv")
    return {"mensaje": "Estudiante registrado exitosamente", "id_estudiante": nuevo_estudiante["id_estudiante"]}

def registrar_docente(nombre: str, idioma: str, genero: str, experiencia: int) -> dict:
    """Necesita nombre, idioma que enseña, genero y años de experiencia del
       docente que se registrara en caso de no proporcionar alguna de las 4
       informaciones requeridas se debe solicitar nuevamente los datos faltantes """
    if not nombre or not idioma or not genero or experiencia is None:
        return {"error": "Faltan datos: se requiere nombre, idioma, género y años de experiencia"}
    if int(experiencia) < 0:
        return {"error": "Los años de experiencia no pueden ser negativos"}
    docente = pd.read_csv(carpeta / "docente.csv")
    nuevo_docente = {
        "id_docente": _siguiente_id(docente, "id_docente"),
        "nombre": nombre.strip(),
        "idioma": idioma.strip(),
        "genero": genero.strip(),
        "anios_experiencia": int(experiencia),
    }
    docente = pd.concat([docente, pd.DataFrame([nuevo_docente])], ignore_index=True)
    _guardar(docente, "docente.csv")
    return {"mensaje": "Docente registrado exitosamente", "id_docente": nuevo_docente["id_docente"]}

def registrar_curso(id_docente: int, nivel: str, precio: float, duracion_semanas: int) -> dict:
    """Se necesita obligatoriamente el id_docente, sin ello no podra avanzar
       a las demas opciones, una vez obtenido el id_docente se debera preguntar
       el nivel y se le debera dar a elegir UNICAMENTE entre (Básico, Intermedio, Avanzado),
       el precio y la duracion en semanas"""
    docentes = pd.read_csv(carpeta / "docente.csv")

    if int(id_docente) not in docentes["id_docente"].values:
        return {"error": f"No existe un docente con id {id_docente}"}
    if nivel not in ("Básico", "Intermedio", "Avanzado"):
        return {"error": "Nivel inválido: debe ser Básico, Intermedio o Avanzado"}
    if float(precio) <= 0 or int(duracion_semanas) <= 0:
        return {"error": "El precio y la duración deben ser mayores que 0"}

    curso = pd.read_csv(carpeta / "curso.csv")
    nuevo_curso = {
        "id_curso": _siguiente_id(curso, "id_curso"),
        "id_docente": int(id_docente),
        "nivel": nivel,
        "precio": float(precio),
        "duracion_semanas": int(duracion_semanas),
    }

    curso = pd.concat([curso, pd.DataFrame([nuevo_curso])], ignore_index=True)
    _guardar(curso, "curso.csv")
    return {"mensaje": "Curso registrado exitosamente", "id_curso": nuevo_curso["id_curso"]}

def metodos_pago_disponibles(mes_inicio: str = "", mes_fin: str = "") -> dict:
    """Devuelve los métodos de pago disponibles (los que aparecen en los pagos
       registrados) y, para cada uno, cuántos pagos se hicieron, cuánto dinero
       se recaudó y su porcentaje del total de pagos. Están ordenados del más
       usado al menos usado. Se puede filtrar por un periodo con mes_inicio y
       mes_fin en formato AAAA-MM (por ejemplo "2026-01"). Si el usuario no
       indica un periodo, se usan todos los pagos."""
    error = _validar_meses(mes_inicio, mes_fin)
    if error:
        return {"error": error}

    pago = _pagos_del_periodo(mes_inicio, mes_fin)
    if pago.empty:
        return {"mensaje": "No hay pagos registrados en ese periodo", "metodos": []}

    cantidad = pago.groupby("metodo_pago")["id_pago"].count().sort_values(ascending=False)
    monto = pago.groupby("metodo_pago")["monto"].sum()
    total_pagos = int(cantidad.sum())

    return {
        "metodos_disponibles": [str(m) for m in cantidad.index],
        "total_pagos": total_pagos,
        "detalle": [
            {"metodo": str(m),
             "cantidad_pagos": int(cantidad[m]),
             "porcentaje": round(float(cantidad[m] / total_pagos * 100), 1),
             "monto_recaudado": round(float(monto[m]), 2)}
            for m in cantidad.index
        ],
        "mas_usado": str(cantidad.idxmax()),
        "menos_usado": str(cantidad.idxmin()),
    }

def total_recaudado(mes_inicio: str = "", mes_fin: str = "") -> dict:
    """Devuelve el total de dinero recaudado por los pagos de los alumnos,
       la cantidad de pagos, el promedio por pago y lo recaudado en cada mes.
       Se puede filtrar por un periodo con mes_inicio y mes_fin en formato
       AAAA-MM (por ejemplo "2026-01" y "2026-03"). Si el usuario no indica
       un periodo, se calcula con todos los pagos. Si el usuario dice el mes
       con palabras (por ejemplo "marzo de 2026"), conviértelo a AAAA-MM."""
    error = _validar_meses(mes_inicio, mes_fin)
    if error:
        return {"error": error}

    pago = _pagos_del_periodo(mes_inicio, mes_fin)
    if pago.empty:
        return {"mensaje": "No hay pagos registrados en ese periodo", "total_recaudado": 0}

    por_mes = pago.groupby("mes")["monto"].sum()

    return {
        "periodo": f"{pago['mes'].min()} a {pago['mes'].max()}",
        "total_recaudado": round(float(pago["monto"].sum()), 2),
        "cantidad_pagos": int(len(pago)),
        "promedio_por_pago": round(float(pago["monto"].mean()), 2),
        "mes_mayor_recaudacion": str(por_mes.idxmax()),
        "mes_menor_recaudacion": str(por_mes.idxmin()),
        "recaudado_por_mes": [
            {"mes": str(mes), "monto": round(float(monto), 2)}
            for mes, monto in por_mes.items()
        ],
    }

def datos_alumno(nombre: str = "", id_estudiante: int = 0) -> dict:
    """Devuelve los datos de un alumno: nombre, edad, id_matricula y curso
       (idioma y nivel) de cada matrícula que tenga.
       Se puede buscar por nombre (o parte del nombre) o por id_estudiante.
       Si el usuario no da ni el nombre ni el id, se le debe pedir uno de los dos.
       Si hay varios alumnos con nombres parecidos, mostrar las opciones y
       preguntar a cuál se refiere."""
    if not nombre and not id_estudiante:
        return {"error": "Falta el dato: se requiere el nombre o el id del estudiante"}

    # Lectura y union de las tablas
    estudiante = pd.read_csv(carpeta / "estudiante.csv")
    matricula = pd.read_csv(carpeta / "matricula.csv")
    horario = pd.read_csv(carpeta / "horario.csv")
    curso = pd.read_csv(carpeta / "curso.csv")
    docente = pd.read_csv(carpeta / "docente.csv")
    datos = estudiante.merge(matricula, on="id_estudiante") \
                      .merge(horario, on="id_horario") \
                      .merge(curso, on="id_curso") \
                      .merge(docente, on="id_docente", suffixes=("_alumno", "_docente"))

    if id_estudiante:
        alumno = datos[datos["id_estudiante"] == int(id_estudiante)]
        solo = estudiante[estudiante["id_estudiante"] == int(id_estudiante)]
    else:
        alumno = datos[datos["nombre_alumno"].str.contains(nombre, case=False, na=False, regex=False)]
        solo = estudiante[estudiante["nombre"].str.contains(nombre, case=False, na=False, regex=False)]

    if alumno.empty:
        if not solo.empty:
            fila = solo.iloc[0]
            return {"mensaje": "El alumno existe pero no tiene matrículas",
                    "id_estudiante": int(fila["id_estudiante"]),
                    "nombre": str(fila["nombre"]),
                    "edad": int(fila["edad"])}
        return {"error": "No se encontró ningún alumno con esos datos"}

    if alumno["id_estudiante"].nunique() > 1:
        opciones = alumno.drop_duplicates("id_estudiante")
        return {"mensaje": "Hay varios alumnos con ese nombre, ¿a cuál te refieres?",
                "opciones": [{"id_estudiante": int(f["id_estudiante"]), "nombre": str(f["nombre_alumno"])}
                             for _, f in opciones.iterrows()]}

    fila = alumno.iloc[0]
    return {
        "id_estudiante": int(fila["id_estudiante"]),
        "nombre": str(fila["nombre_alumno"]),
        "edad": int(fila["edad"]),
        "matriculas": [
            {"id_matricula": int(f["id_matricula"]),
             "curso": f"{f['idioma']} {f['nivel']}",
             "docente": str(f["nombre_docente"])}
            for _, f in alumno.iterrows()
        ],
    }

def mostrar_listadoProfesor_Idioma(idioma: str) -> dict:
    """Devuelve la lista de profesores (id y nombre) que enseñan un idioma
       específico. Si el idioma no existe, devuelve los idiomas disponibles."""
    docente = pd.read_csv(carpeta / "docente.csv")
    idioma_ok = _buscar_idioma(idioma, docente)
    if idioma_ok is None:
        return {"error": f"El idioma '{idioma}' no existe",
                "idiomas_disponibles": [str(i) for i in docente["idioma"].dropna().unique()]}

    filtrados = docente[docente["idioma"] == idioma_ok]
    return {
        "idioma": str(idioma_ok),
        "cantidad": int(len(filtrados)),
        "profesores": [{"id_docente": int(f["id_docente"]), "nombre": str(f["nombre"])}
                       for _, f in filtrados.iterrows()],
    }

def mostrar_listadoAlumnos_Idioma(idioma: str) -> dict:
    """Devuelve la lista de alumnos (id y nombre) matriculados en un idioma
       específico. Si el idioma no existe, devuelve los idiomas disponibles."""
    estudiante = pd.read_csv(carpeta / "estudiante.csv")
    matricula = pd.read_csv(carpeta / "matricula.csv")
    horario = pd.read_csv(carpeta / "horario.csv")
    curso = pd.read_csv(carpeta / "curso.csv")
    docente = pd.read_csv(carpeta / "docente.csv")

    idioma_ok = _buscar_idioma(idioma, docente)
    if idioma_ok is None:
        return {"error": f"El idioma '{idioma}' no existe",
                "idiomas_disponibles": [str(i) for i in docente["idioma"].dropna().unique()]}

    datos = estudiante.merge(matricula, on="id_estudiante") \
                      .merge(horario, on="id_horario") \
                      .merge(curso, on="id_curso") \
                      .merge(docente, on="id_docente", suffixes=("_alumno", "_docente"))
    alumnos = datos[datos["idioma"] == idioma_ok].drop_duplicates("id_estudiante")

    return {
        "idioma": str(idioma_ok),
        "cantidad": int(len(alumnos)),
        "alumnos": [{"id_estudiante": int(f["id_estudiante"]), "nombre": str(f["nombre_alumno"])}
                    for _, f in alumnos.iterrows()],
    }

def crear_grafico(
    titulo: str, tipo: str, etiquetas: list[str], valores: list[float] ) -> dict:
    """Muestra un gráfico al usuario. Úsala cuando pidan graficar algo.
    Args:
        titulo: título del gráfico.
        tipo: 'bar' (barras), 'line' (líneas) o 'pie' (torta).
        etiquetas: nombres de cada categoría.
        valores: número de cada categoría, en el mismo orden.
    """
    if tipo not in ("bar", "line", "pie"):
        return {"error": "Tipo inválido: debe ser 'bar', 'line' o 'pie'"}
    if len(etiquetas) != len(valores):
        return {"error": "etiquetas y valores deben tener la misma cantidad de elementos"}
    return {
        "titulo": titulo,
        "tipo": tipo,
        "etiquetas": etiquetas,
        "valores": valores,
    }


# Instrucciones del agente
INSTRUCCION = """
ROL
Eres el asistente de un centro de idiomas, tu nombre es uNex.
Respondes en español, con frases cortas, sin listas ni símbolos,
porque tu respuesta puede leerse en voz alta.

REGLAS GENERALES
1. Usa siempre las herramientas para consultar los datos.
2. No inventes información.
3. Los montos están en soles (S/).
4. Si una herramienta devuelve un error, explícalo con tus palabras y pide el dato correcto.

ALUMNOS
- Nunca le pidas el id al usuario: él te da el nombre.
- Con el nombre, usa datos_alumno para obtener el id, la edad y sus matrículas.
- Si hay varios alumnos con nombres parecidos, nombra las opciones y pregunta a cuál se refiere.
- Para saber qué alumnos estudian un idioma, usa mostrar_listadoAlumnos_Idioma.

DOCENTES
- Para saber qué profesores enseñan un idioma, usa mostrar_listadoProfesor_Idioma.
- Si el idioma no existe, menciona los idiomas disponibles que devuelve la herramienta.

REGISTROS
- Para registrar un alumno necesitas: nombre, género y edad.
- Para registrar un docente necesitas: nombre, idioma que enseña, género y años de experiencia.
- Para registrar un curso necesitas: docente, nivel, precio y duración en semanas.
  Pregunta el nombre del docente y su idioma, y obtén su id con mostrar_listadoProfesor_Idioma.
  El idioma del curso es el que enseña el docente.
- Niveles válidos: Básico, Intermedio y Avanzado. Escríbelos exactamente así.
- Géneros válidos: Femenino y Masculino.
- Pregunta siempre lo que falte. No supongas ningún dato.

PAGOS Y RECAUDACIÓN
- Para el dinero recaudado, usa total_recaudado.
- Para los métodos de pago, usa metodos_pago_disponibles.
- Métodos de pago registrados: Yape, Plin, Tarjeta, Transferencia y Efectivo.
- Los periodos se pasan en formato AAAA-MM. Si el usuario dice "marzo de 2026", usa 2026-03.
- Para el total de matrículas, usa matriculas_totales.

CONFIRMACIÓN
- Antes de registrar un alumno, un docente o un curso, repite los datos y pregunta: ¿Confirmas?
- Registra solo si el usuario responde que sí.

GRÁFICOS
- Obtén los datos con una herramienta y luego llama a crear_grafico.
- Usa 'bar' para comparar, 'line' para evolución en el tiempo y 'pie' para porcentajes.
"""

root_agent = Agent(
    name="agente_centro_idiomas",
    model=modelo,
    instruction=INSTRUCCION,
    tools=[
        matriculas_totales,
        registrar_alumno,
        registrar_docente,
        registrar_curso,
        metodos_pago_disponibles,
        total_recaudado,
        datos_alumno,
        mostrar_listadoProfesor_Idioma,
        mostrar_listadoAlumnos_Idioma,
        crear_grafico,
    ],
)
