#############################
# 🔹 Librerías
#############################
import os
import json
import nest_asyncio
import asyncio
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

#############################
# 🔹 Configuración inicial
#############################
nest_asyncio.apply()
app = Flask(__name__)
CMP_URL = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/index.php"

#############################
# 🔹 Función principal
#############################
async def run_cmp(cmp_number):
    """Automatiza la búsqueda y extracción de datos del CMP (versión Cloud Run estable)."""
    print(f"\n========== INICIO BÚSQUEDA CMP {cmp_number} ==========")

    async with async_playwright() as p:
        # ✅ HEADLESS + OPCIONES "STEALTH" para entornos sin interfaz
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-gpu",
                "--single-process",
                "--no-zygote"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        try:
            # 1️⃣ Cargar página principal
            print("[INFO] Cargando página principal...")
            await page.goto(CMP_URL, wait_until="domcontentloaded", timeout=60000)

            # Espera adicional para asegurar carga completa
            await page.wait_for_timeout(1500)

            # 2️⃣ Esperar campo CMP visible
            print("[INFO] Esperando campo CMP...")
            await page.wait_for_selector('input[name="cmp"]', timeout=30000)

            # 3️⃣ Ingresar CMP
            print(f"[INFO] Ingresando CMP: {cmp_number}")
            await page.fill('input[name="cmp"]', str(cmp_number))

            # 4️⃣ Presionar botón “Buscar”
            print("[INFO] Presionando botón Buscar...")
            await page.click('input.btn.btn-sub[type="submit"]')

            # Esperar carga de la siguiente página
            await page.wait_for_load_state("networkidle", timeout=90000)
            print("[INFO] Página de resultados cargada correctamente")

            # 5️⃣ Click en “Detalle”
            print("[INFO] Buscando enlace de detalle...")
            await page.wait_for_selector('a[href*="datos-colegiado-detallado"]', timeout=20000)
            await page.click('a[href*="datos-colegiado-detallado"]')

            print("[INFO] Entrando a la página de detalle...")
            await page.wait_for_load_state("load", timeout=30000)

            # 6️⃣ Obtener HTML de la página final
            html = await page.content()
            await browser.close()
            print("[INFO] HTML del detalle obtenido correctamente")

            # 7️⃣ Analizar con BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Datos principales
            cmp_row = soup.find("tr", class_="cabecera_tr2")
            if cmp_row:
                cols = cmp_row.find_all("td")
                cmp_number_val = cols[0].get_text(strip=True) if len(cols) >= 1 else "No existe dato"
                apellidos = cols[1].get_text(strip=True) if len(cols) >= 2 else "No existe dato"
                nombres = cols[2].get_text(strip=True) if len(cols) >= 3 else "No existe dato"
            else:
                cmp_number_val, apellidos, nombres = "No existe dato", "No existe dato", "No existe dato"

            # Habilitación
            habil = soup.find("td", string=lambda x: x and any(s in x for s in ["HÁBIL", "NO HÁBIL", "FALLECIDO"]))
            habilitacion_del_medico = habil.get_text(strip=True) if habil else "No existe dato"

            # Consejo Regional
            consejo = soup.find("td", string=lambda x: x and "CONSEJO REGIONAL" in x)
            consejo_regional = consejo.get_text(strip=True) if consejo else "No existe dato"

            # Especialidades
            especialidades = []
            tabla_esp = soup.find_all("tr", class_="cabecera_tr2")
            for fila in tabla_esp:
                cols = [c.get_text(strip=True) for c in fila.find_all("td")]
                if len(cols) == 4 and all(cols):
                    especialidades.append({
                        "registro": cols[0],
                        "tipo": cols[1],
                        "codigo": cols[2],
                        "fecha": cols[3],
                    })

            # 🔸 Estructura final
            data = {
                "cmp_number": cmp_number_val,
                "apellidos": apellidos,
                "nombres": nombres,
                "habilitacion_del_medico": habilitacion_del_medico,
                "especialidades": especialidades,
                "consejo_regional": consejo_regional
            }

            print("[INFO] ✅ Extracción completada con éxito")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return data

        except Exception as e:
            print(f"[ERROR] ❌ Error durante scraping: {e}")
            await browser.close()
            return {"error": str(e)}

#############################
# 🔹 Endpoint Flask
#############################
@app.route("/api/get_cmp_info", methods=["POST"])
def get_cmp_info():
    data = request.get_json()
    cmp_number = data.get("cmp")
    if not cmp_number:
        return jsonify({"error": "Debe enviar el número de colegiatura 'cmp'"}), 400

    print(f"[FLASK] Solicitud recibida CMP: {cmp_number}")
    try:
        result = asyncio.run(run_cmp(cmp_number))
        return jsonify(result), 200
    except Exception as e:
        print(f"[FLASK ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

#############################
# 🔹 Ejecución
#############################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
