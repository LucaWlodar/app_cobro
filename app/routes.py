import os
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import requests

from . import db
from .models import User, Product, Order, OrderItem
from .forms import RegisterForm, LoginForm, ProductForm

# ---------- AUTENTICACIÓN ----------
def _get_user_order(create_if_missing=True):
    """Devuelve el carrito (Order) del usuario actual."""
    if not current_user.is_authenticated:
        return None

    order = Order.query.filter_by(user_id=current_user.id, status='pending').first()
    if not order and create_if_missing:
        order = Order(user_id=current_user.id, status='pending')
        db.session.add(order)
        db.session.commit()
    return order

# ---------- RUTAS PRINCIPALES ----------
def index():
    products = Product.query.all()
    return render_template("index.html", products=products)

# ---------- REGISTRO / LOGIN ----------
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Usuario ya existe", "warning")
            return redirect(url_for('register'))
        user = User(username=form.username.data, password=generate_password_hash(form.password.data))
        db.session.add(user)
        db.session.commit()
        flash("Registrado correctamente. Iniciá sesión.", "success")
        return redirect(url_for('login'))
    return render_template("register.html", form=form)

def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash("Bienvenido, " + user.username, "success")
            return redirect(url_for('index'))
        flash("Credenciales incorrectas", "danger")
    return render_template("login.html", form=form)

@login_required
def logout():
    logout_user()
    flash("Cerraste sesión", "info")
    return redirect(url_for('index'))

# ---------- CRUD DE PRODUCTOS ----------
@login_required
def products():
    prods = Product.query.all()
    return render_template("products.html", products=prods)

@login_required
def new_product():
    form = ProductForm()
    if form.validate_on_submit():
        p = Product(name=form.name.data, description=form.description.data, price=form.price.data)
        db.session.add(p)
        db.session.commit()
        flash("Producto creado", "success")
        return redirect(url_for('products'))
    return render_template("product_form.html", form=form, action="Nuevo producto")

@login_required
def edit_product(pid):
    p = Product.query.get_or_404(pid)
    form = ProductForm(obj=p)
    if form.validate_on_submit():
        p.name = form.name.data
        p.description = form.description.data
        p.price = form.price.data
        db.session.commit()
        flash("Producto actualizado", "success")
        return redirect(url_for('products'))
    return render_template("product_form.html", form=form, action="Editar producto")

@login_required
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash("Producto eliminado", "info")
    return redirect(url_for('products'))

# ---------- CARRITO ----------
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        quantity = int(request.form.get("quantity", 1))
        if quantity < 1:
            raise ValueError
    except ValueError:
        flash("Cantidad inválida", "warning")
        return redirect(url_for('index'))

    order = _get_user_order(True)
    item = next((i for i in order.items if i.product_id == product.id), None)
    if item:
        item.quantity += quantity
    else:
        new_item = OrderItem(order_id=order.id, product_id=product.id, quantity=quantity)
        db.session.add(new_item)
    db.session.commit()
    flash("Agregado al carrito", "success")
    return redirect(url_for('index'))

@login_required
def remove_from_cart(item_id):
    order = _get_user_order(False)
    if not order:
        flash("No hay un carrito activo", "warning")
        return redirect(url_for("cart"))

    item = OrderItem.query.get_or_404(item_id)
    if item.order.user_id != current_user.id:
        flash("No puedes modificar otro carrito", "danger")
        return redirect(url_for("cart"))

    db.session.delete(item)
    db.session.commit()
    flash("Producto eliminado del carrito", "info")
    return redirect(url_for("cart"))

@login_required
def cart():
    order = _get_user_order(False)
    return render_template("cart.html", order=order)

@login_required
def checkout():
    order = _get_user_order(False)
    if not order or not order.items:
        flash("Carrito vacío", "warning")
        return redirect(url_for('index'))
    return render_template("order.html", order=order)

# ---------- PAGO LOCAL ----------
@login_required
def pay_local(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Acceso denegado", "danger")
        return redirect(url_for('index'))

    order.status = 'paid'
    db.session.commit()
    flash("Pedido marcado como pagado", "success")
    return render_template("payment_result.html", order=order, method="Simulador local", result="success")

# ---------- MERCADO PAGO ----------
@login_required
def mp_create_preference(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Acceso denegado", "danger")
        return redirect(url_for('index'))

    if not order.items:
        flash("Pedido vacío", "warning")
        return redirect(url_for('checkout'))

    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    if not access_token:
        flash("Token de Mercado Pago faltante", "danger")
        return redirect(url_for('checkout'))

    items = [
        {
            "title": it.product.name,
            "quantity": it.quantity,
            "unit_price": float(it.product.price)
        } for it in order.items
    ]

    payload = {
        "items": items,
        "back_urls": {
            "success": request.host_url.rstrip('/') + url_for('mp_success', order_id=order.id),
            "failure": request.host_url.rstrip('/') + url_for('mp_failure', order_id=order.id),
            "pending": request.host_url.rstrip('/') + url_for('mp_pending', order_id=order.id)
        }
        # Quitamos "auto_return" porque genera error 400 en local
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    mp_url = "https://api.mercadopago.com/checkout/preferences"
    resp = requests.post(mp_url, json=payload, headers=headers)

    if resp.status_code in (200, 201):
        init_point = resp.json().get("init_point")
        return redirect(init_point)
    else:
        flash("Error creando preferencia Mercado Pago: " + resp.text, "danger")
        return redirect(url_for('checkout'))

# ---------- CALLBACKS ----------
@login_required
def mp_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id == current_user.id:
        order.status = 'paid'
        db.session.commit()
    return render_template("payment_result.html", order=order, method="Mercado Pago", result="success")

@login_required
def mp_failure(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("payment_result.html", order=order, method="Mercado Pago", result="failure")

@login_required
def mp_pending(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("payment_result.html", order=order, method="Mercado Pago", result="pending")

# ---------- REGISTRO DE RUTAS ----------
from flask import current_app as app
app.add_url_rule("/", "index", index)
app.add_url_rule("/register", "register", register, methods=["GET","POST"])
app.add_url_rule("/login", "login", login, methods=["GET","POST"])
app.add_url_rule("/logout", "logout", logout)
app.add_url_rule("/products", "products", products)
app.add_url_rule("/product/new", "new_product", new_product, methods=["GET","POST"])
app.add_url_rule("/product/edit/<int:pid>", "edit_product", edit_product, methods=["GET","POST"])
app.add_url_rule("/product/delete/<int:pid>", "delete_product", delete_product, methods=["POST"])
app.add_url_rule("/add_to_cart/<int:product_id>", "add_to_cart", add_to_cart, methods=["POST"])
app.add_url_rule("/remove_from_cart/<int:item_id>", "remove_from_cart", remove_from_cart, methods=["POST"])
app.add_url_rule("/cart", "cart", cart)
app.add_url_rule("/order/checkout", "checkout", checkout)
app.add_url_rule("/order/pay_local/<int:order_id>", "pay_local", pay_local, methods=["POST"])
app.add_url_rule("/order/mp_create_preference/<int:order_id>", "mp_create_preference", mp_create_preference, methods=["POST"])
app.add_url_rule("/mp/success/<int:order_id>", "mp_success", mp_success)
app.add_url_rule("/mp/failure/<int:order_id>", "mp_failure", mp_failure)
app.add_url_rule("/mp/pending/<int:order_id>", "mp_pending", mp_pending)
