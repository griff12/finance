import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    symbols = db.execute("SELECT DISTINCT symbol FROM purchases WHERE user_id=?", session["user_id"])
    shares = {}
    price = {}
    value = {}
    total = 0
    for symbol in symbols:
        share = db.execute("SELECT SUM(shares) FROM purchases WHERE symbol = ?", symbol['symbol'])
        shares[symbol['symbol']] = share[0]['SUM(shares)']
        stock = lookup(symbol['symbol'])
        price[symbol['symbol']] = usd(stock['price'])
        value[symbol['symbol']] = usd(stock['price'] * shares[symbol['symbol']])
        total += stock['price'] * shares[symbol['symbol']]

    users = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    for user in users:
        cash = (usd(user["cash"]))
        total += user["cash"]

    total = usd(total)

    return render_template("index.html", symbols=symbols, shares=shares, price=price, value=value, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")

    else:
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Invalid symbol.", 400)

        if request.form.get("shares") < "0":
            return apology("Enter a positive number", 400)

        try:
            int(request.form.get("shares"))
        except ValueError:
            return apology("Enter a whole number", 400)

        user_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])

        # Check if user has enough cash to make purchase
        if user_cash[0]["cash"] < stock["price"] * int(request.form.get("shares")):
            return apology("You do not have enough money to make this purchase", 400)

        # Update purchases table
        row = db.execute("SELECT shares FROM purchases WHERE symbol = ? and user_id = ?", 
                         request.form.get("symbol"), session["user_id"])

        if row:
            user_shares = row[0]['shares']
            user_shares += int(request.form.get("shares"))
        else:
            user_shares = int(request.form.get("shares"))

        db.execute("INSERT OR REPLACE INTO purchases (user_id, symbol, price, shares) VALUES(?, ?, ?, ?)", 
                   session["user_id"], request.form.get("symbol"), stock["price"], user_shares)
        db.execute("INSERT INTO trans (type, symbol, price, shares, user_id) VALUES(?, ?, ?, ?, ?)", "BOUGHT", 
                   request.form.get("symbol"), stock["price"], int(request.form.get("shares")), session["user_id"])
        
        # Update amount of cash available to user
        user_cash[0]['cash'] = user_cash[0]['cash'] - stock["price"] * int(request.form.get("shares"))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash[0]['cash'], session['user_id'])

        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM trans WHERE user_id = ?", session["user_id"])

    return render_template("history.html", rows=rows)
    

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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

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

    if request.method == "GET":
        return render_template("quote.html")

    else:
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Invalid symbol.", 400)
        return render_template("quoted.html", symbol=stock["symbol"], company_name=stock["name"], price=usd(stock["price"]))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        # Require a unique username
        if not request.form.get("username"):
            return apology("must provide username", 400)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if rows:
            return apology("username already taken", 400)

        # Require password and confirmation fields match
        if not request.form.get("password"):
            return apology("must provide password", 400)

        if not request.form.get("confirmation"):
            return apology("must re-enter password", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Add user to database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        rows = db.execute("SELECT DISTINCT symbol FROM purchases WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", rows=rows)

    else:
        shares = int(request.form.get("shares"))
        symbol = request.form.get("symbol")
        user_shares = db.execute("SELECT SUM(shares) FROM purchases WHERE symbol = ? AND user_id = ?", 
                                 symbol, session["user_id"])[0]["SUM(shares)"]
        new_shares = user_shares - shares

        if new_shares < 0:
            return apology("You do not have enough shares to complete this transaction", 400)

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        new_cash = cash + (shares * lookup(symbol)['price'])

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])
        db.execute("UPDATE purchases SET shares = ? WHERE symbol = ?", new_shares, symbol)
        db.execute("DELETE FROM purchases WHERE shares = 0")
        db.execute("INSERT INTO trans (type, symbol, price, shares, user_id) VALUES(?, ?, ?, ?, ?)", "SOLD", 
                   request.form.get("symbol"), lookup(symbol)['price'], int(request.form.get("shares")), session["user_id"])

        return redirect("/")
        

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
