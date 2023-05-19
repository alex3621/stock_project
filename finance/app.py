import os
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from helpers import apology, login_required, lookup, usd
import requests


# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# adding database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.sqlite3"

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure db for sqlalchemy
db = SQLAlchemy(app)


class users(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    username = db.Column("username", db.String(100), nullable=False)
    hash = db.Column("hash", db.String(200), nullable=False)
    stocks = db.Column("stocks", db.PickleType, nullable=True)

    def __init__(self, username, hash, stocks):
        self.username = username
        self.hash = hash
        self.stocks = stocks


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


global stock_list
stock_list = {}


@app.route("/")
@login_required
def index():
    global stock_list
    if not stock_list:
        stock_list = requests.get("https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2023-05-10?adjusted=true&apiKey=YuCUc9xPrsUFwddoEubn0vpNb2glg2ro")
        stock_list = stock_list.json()
    return render_template("index.html")


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "GET":
        return render_template("add.html")

    else:
        found = False
        entered_stock = request.form.get("stock")
        for data in stock_list["results"]:
            if data["T"] == entered_stock:
                found = True
        if not entered_stock:
            return apology("no symbols entered")
        elif not found:
            return apology("no match found with the entered symtol")
        else:
            user_id = session["user_id"]
            userStockList = users.query.filter_by(id=user_id).first().stocks
            if entered_stock in userStockList:
                flash("Enetered stock already inside your profile")
                return redirect("add")
            else:
                userStockList.append(entered_stock)
                users.query.filter_by(id=user_id).first().stocks = userStockList
                db.session.commit()
                flash("successfully added stock to your profile")
                return redirect("/")


@app.route("/remove", methods=["GET", "POST"])
@login_required
def remove():
    if request.method == "GET":
        return render_template("remove.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    user_id = session["user_id"]
    stock_symbol = request.form.get("symbol")
    buy_shares = request.form.get("shares")
    quote = lookup(request.form.get("symbol"))
    cash_rows = db.execute("SELECT cash from users WHERE id=?", (user_id))
    now = datetime.now()
    if request.method == "POST":
        if not quote:
            return apology("invalid stock symbol")
        elif not request.form.get("symbol"):
            return apology("no stock symbol")
        elif not request.form.get("shares"):
            return apology("Please enter amount")
        elif not buy_shares.isdigit():
            return apology("not a positive integer", 400)
        elif cash_rows[0]["cash"] < (quote["price"] * int(request.form.get("shares"))):
            return apology("Not enough funds")
        else:
            db.execute(
                "INSERT INTO HISTORY (symbol, shares, price, action, date, time, id) VALUES(?, ?, ?, ?, ?, ?, ?)",
                quote["symbol"],
                request.form.get("shares"),
                quote["price"],
                "buy",
                date.today(),
                now.strftime("%H:%M:%S"),
                user_id,
            )
            if not db.execute(
                "SELECT * FROM STOCKS where id=? AND symbol=?", user_id, stock_symbol
            ):
                db.execute(
                    "INSERT INTO STOCKS (id, symbol, shares) VALUES(?, ?, ?)",
                    user_id,
                    stock_symbol,
                    request.form.get("shares"),
                )
            else:
                db.execute(
                    "UPDATE STOCKS SET shares=shares+? WHERE id=? AND symbol=?",
                    buy_shares,
                    user_id,
                    stock_symbol,
                )
            db.execute(
                "UPDATE users SET cash=cash-(?*?) WHERE id=?",
                quote["price"],
                buy_shares,
                user_id,
            )
            flash("purchase successful")
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        user_id = session["user_id"]
        symbols = db.execute("SELECT symbol FROM STOCKS WHERE id=?", user_id)
        return render_template("sell.html", symbols=symbols)

    user_id = session["user_id"]
    symbols = db.execute("SELECT symbol FROM STOCKS WHERE id=?", user_id)
    stock_symbol = request.form.get("symbol")
    sell_shares = request.form.get("shares")
    quote = lookup(request.form.get("symbol"))
    user_stock = db.execute(
        "SELECT shares FROM STOCKS WHERE id=? AND symbol=?", user_id, stock_symbol
    )
    now = datetime.now()

    if request.method == "POST":
        if not quote:
            return apology("invalid stock symbol")
        elif not stock_symbol:
            return apology("no stock symbol")
        elif not sell_shares:
            return apology("Please enter amount")
        elif int(user_stock[0]["shares"]) < int(sell_shares):
            return apology("Not enough shares to sell")
        else:
            db.execute(
                "INSERT INTO HISTORY (symbol, shares, price, action, date, time, id) VALUES(?, ?, ?, ?, ?, ?, ?)",
                quote["symbol"],
                request.form.get("shares"),
                quote["price"],
                "sell",
                date.today(),
                now.strftime("%H:%M:%S"),
                user_id,
            )
            db.execute(
                "UPDATE STOCKS SET shares=shares-? WHERE id=? AND symbol=?",
                sell_shares,
                user_id,
                stock_symbol,
            )
            db.execute(
                "UPDATE users SET cash=cash+(?*?) WHERE id=?",
                quote["price"],
                sell_shares,
                user_id,
            )
            flash("action successful")
            return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        else:
            form_username = request.form.get("username")
            form_password = request.form.get("password")
            rows = users.query.filter_by(username=form_username).first()
            # print(check_password_hash(rows[0]["hash"], password))

        # Ensure username exists and password is correct
        if not rows or not check_password_hash(rows.hash, form_password):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows.id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("please enter symbol")

        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("invalid symbol")

        else:
            return render_template("quoted.html", quote=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    else:
        form_username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not form_username or not password or not confirmation:
            return apology("must fill out form", 400)

        username_check = users.query.filter_by(username=form_username).first()

        if confirmation != password:
            return apology("confirmation not correct")
        elif username_check:
            return apology("username already taken")
        else:
            password = generate_password_hash(
                password, method="pbkdf2:sha1", salt_length=8
            )
            stocks = []
            user = users(form_username, password, stocks)
            db.session.add(user)
            db.session.commit()
            flash("successful registration")
            return redirect("/")
