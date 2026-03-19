import os
import base64
from io import BytesIO
from urllib.parse import quote
from uuid import uuid4

import mercadopago
import qrcode
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    flash
)

from database import (
    init_db,
    upsert_user,
    get_user_by_email,
    is_user_premium,
    activate_premium,
    save_payment
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)


def limpar_numero(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def gerar_qrcode_base64(link: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)

    imagem = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@app.route("/", methods=["GET", "POST"])
def index():
    init_db()

    erro = ""
    link_gerado = ""
    qrcode_base64 = ""

    name = session.get("name", "")
    email = session.get("email", "")
    codigo_pais = "55"
    numero = ""
    mensagem = ""

    premium_mode = False
    if email:
        premium_mode = is_user_premium(email)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        codigo_pais = limpar_numero(request.form.get("codigo_pais", ""))
        numero = limpar_numero(request.form.get("numero", ""))
        mensagem = request.form.get("mensagem", "").strip()

        if not name:
            erro = "Informe seu nome."
        elif not email:
            erro = "Informe seu e-mail."
        elif not codigo_pais:
            erro = "Informe o código do país."
        elif not numero:
            erro = "Informe um número válido."
        else:
            upsert_user(name, email)
            session["name"] = name
            session["email"] = email

            premium_mode = is_user_premium(email)

            numero_completo = f"{codigo_pais}{numero}"
            link_gerado = f"https://wa.me/{numero_completo}"

            if mensagem:
                link_gerado += f"?text={quote(mensagem)}"

            session["last_link"] = link_gerado

            if premium_mode:
                qrcode_base64 = gerar_qrcode_base64(link_gerado)

    return render_template(
        "index.html",
        erro=erro,
        link_gerado=link_gerado,
        qrcode_base64=qrcode_base64,
        premium_mode=premium_mode,
        name=name,
        email=email,
        codigo_pais=codigo_pais,
        numero=numero,
        mensagem=mensagem
    )

@app.route("/create-checkout", methods=["POST"])
def create_checkout():
    email = session.get("email")
    name = session.get("name")

    if not email or not name:
        flash("Preencha nome e e-mail antes de assinar o plano Pro.")
        return redirect(url_for("index"))

    external_reference = f"{email}|{uuid4()}"

    preference_data = {
        "items": [
            {
                "title": "ZapLink Pro - 30 dias",
                "quantity": 1,
                "unit_price": 9.90,
                "currency_id": "BRL"
            }
        ],
        "payer": {
            "name": name,
            "email": email
        },
        "external_reference": external_reference
    }

    try:
        response = sdk.preference().create(preference_data)
        print("RESPOSTA MERCADO PAGO:")
        print(response)

        data = response.get("response", {})
        init_point = data.get("sandbox_init_point") or data.get("init_point")

        if not init_point:
            flash(f"Erro ao criar checkout: {data}")
            return redirect(url_for("index"))

        return redirect(init_point)

    except Exception as e:
        print("ERRO AO CRIAR CHECKOUT:", str(e))
        flash(f"Erro ao criar checkout: {str(e)}")
        return redirect(url_for("index"))

@app.route("/success")
def success():
    email = session.get("email")
    premium_mode = is_user_premium(email) if email else False
    return render_template("success.html", premium_mode=premium_mode)


@app.route("/cancel")
def cancel():
    return render_template("cancel.html")


@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():
    payload = request.get_json(silent=True) or {}
    query_type = request.args.get("type")
    topic = payload.get("type") or query_type or payload.get("topic")

    data_obj = payload.get("data", {})
    payment_id = data_obj.get("id") or request.args.get("data.id") or request.args.get("id")

    if topic != "payment" or not payment_id:
        return {"status": "ignored"}, 200

    payment_response = sdk.payment().get(payment_id)
    payment = payment_response.get("response", {})

    status = payment.get("status")
    external_reference = payment.get("external_reference", "")
    payer = payment.get("payer", {}) or {}
    email = payer.get("email")

    if not email and external_reference and "|" in external_reference:
        email = external_reference.split("|", 1)[0]

    if not email:
        return {"status": "missing_email"}, 200

    user = get_user_by_email(email)
    if not user:
        upsert_user(email.split("@")[0], email)

    save_payment(
        email=email,
        mp_payment_id=str(payment_id),
        status=status or "unknown",
        external_reference=external_reference or ""
    )

    if status == "approved":
        activate_premium(email, days=30)

    return {"status": "ok"}, 200


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()