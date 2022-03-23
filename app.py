import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session['user_id']
    symbols = db.execute("SELECT DISTINCT(symbol) FROM transactions WHERE user_id=? AND type=?", user_id, "buy")

    holdings = []

    for dict in symbols:

        # Get the Net Amount of shares for each symbol
        symbol = dict['symbol']
        shares_bought = db.execute(
            "SELECT SUM(shares) as shares FROM transactions WHERE user_id=? AND symbol=? AND type=?", user_id, symbol, "buy")[0]['shares']
        shares_sold = db.execute(
            "SELECT SUM(shares) as shares FROM transactions WHERE user_id=? AND symbol=? AND type=?", user_id, symbol, "sell")[0]['shares']

        # breakpoint()

        if shares_sold == None:
            holdings.append({'symbol': symbol,
                            'shares': shares_bought})

        elif shares_bought > shares_sold:
            amount = shares_bought - shares_sold
            holdings.append({'symbol': symbol,
                            'shares': amount})

    cash = db.execute("SELECT cash FROM users WHERE id=?", session['user_id'])[0]['cash']
    total = cash

    for holding in holdings:
        quote = lookup(holding['symbol'])
        holding['name'] = quote['name']
        holding['total'] = round(holding['shares'] * quote['price'], 2)
        total += holding['total']
        holding['price'] = usd(quote['price'])
        holding['total'] = usd(holding['total'])

    return render_template(
        "/index.html", holdings=holdings, cash=usd(cash), total=usd(total))


@app.route("/")
def image():
    # Generate the figure **without using pyplot**.
    fig = Figure()
    ax = fig.subplots()
    ax.plot([1, 2])
    # Save it to a temporary buffer.
    buf = BytesIO()
    fig.savefig(buf, format="png")
    # Embed the result in the html output.
    data = base64.b64encode(buf.getbuffer()).decode("ascii")
    return f"<img src='data:image/png;base64,{data}'/>"


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Get the variables loaded in the form
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        try:
            shares = float(shares)
        except:
            return apology("Not numeric input entered", 400)

        # breakpoint()
        if (shares % 1) != 0:
            return apology("The input is not an integer", 400)

        if not shares > 0:
            return apology("The input must be a positive integer", 400)

        # Search stock price in IEX Cloud
        quote = lookup(symbol)

        # Return apology if symbol is invalid
        if quote == None:
            return apology("invalid symbol", 400)

        # Return apology if user didn't load a positive integer
        if not shares > 0:
            return apology("the input is not a positive integer", 400)

        # Store the price of the stock
        price = quote["price"]

        # Query the amount of cash of the user
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id=?", user_id)[0]["cash"]

        # Return an apology if the user can't afford the transaction
        if (price * shares) > cash:
            return apology("Not enough cash to complete transaction", 403)

        date = datetime.datetime.now()

        # Store each transaction in the database
        db.execute("INSERT INTO transactions (user_id, shares, price, date, symbol, type) VALUES(?,?,?,?,?,?)",
                   user_id, shares, price, date, symbol, "buy")

        # Update cash availability of the user
        new_cash = cash - (price * shares)

        db.execute("UPDATE users SET cash=? WHERE id=?", new_cash, user_id)

        # When a purchase is complete, redirect the user back to the index page
        return redirect("/")

    return render_template("/buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM transactions WHERE user_id=?", session['user_id'])

    for transaction in history:
        transaction['price'] = usd(transaction['price'])

    return render_template("/history.html", history=history)


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
    """Get stock quote."""
    if request.method == "POST":

        symbol = request.form.get("symbol")

        quote = lookup(symbol)

        if quote == None:
            return apology("invalid symbol / Didn't find stock price", 400)

        name = quote["name"]
        price = usd(quote["price"])

        return render_template(
            "quoted.html", name=name, symbol=symbol, price=price)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide a username", 400)

        username = request.form.get("username")
        search_username = db.execute("SELECT * FROM users WHERE username=?", username)
        # breakpoint()
        if not search_username == []:
            return apology("Selected username already exist", 400)

        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide a password and confirmation", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password doesn't match confirmation", 400)

        password_hash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", username, password_hash)

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session['user_id']
    symbols = db.execute("SELECT DISTINCT(symbol) FROM transactions WHERE user_id=? AND type=?", user_id, "buy")

    if request.method == "POST":
        # Check whether the selected stock exist in the user's portfolio
        symbol = request.form.get("symbol")

        shares_bought = db.execute(
            "SELECT SUM(shares) as shares FROM transactions WHERE user_id=? AND symbol=? AND type=?", user_id, symbol, "buy")[0]['shares']
        shares_sold = db.execute(
            "SELECT SUM(shares) as shares FROM transactions WHERE user_id=? AND symbol=? AND type=?", user_id, symbol, "sell")[0]['shares']
        # breakpoint()

        if shares_sold == None:
            shares = shares_bought
        elif shares_bought == shares_sold:
            return apology("User doesn't own selected stock", 403)
        else:
            shares = shares_bought - shares_sold

        shares_to_sell = request.form.get("shares")

        try:
            shares_to_sell = float(shares_to_sell)
        except:
            return apology("Not numeric input entered", 400)

        # breakpoint()
        if (shares_to_sell % 1) != 0:
            return apology("The input is not an integer", 400)

        if not shares_to_sell > 0:
            return apology("The input must be a positive integer", 400)

        if shares_to_sell > shares:
            return apology("User doesn't have such amount of shares", 400)

        # Search stock price in IEX Cloud
        quote = lookup(symbol)

        price = quote['price']

        cash = db.execute("SELECT cash FROM users WHERE id=?", user_id)[0]["cash"]

        date = datetime.datetime.now()

        # Store each transaction in the database
        db.execute("INSERT INTO transactions (user_id, shares, price, date, symbol, type) VALUES(?,?,?,?,?,?)",
                   user_id, shares_to_sell, price, date, symbol, "sell")

        # Update cash availability of the user
        new_cash = cash + (price * shares_to_sell)

        db.execute("UPDATE users SET cash=? WHERE id=?", new_cash, user_id)

        return redirect("/")

    return render_template("/sell.html", symbols=symbols)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """
        Deposit Cash into the account
    """

    if request.method == "POST":
        cash = request.form.get("usd")

        if cash == "":
            return apology("You must select a deposit amount", 400)

        try:
            cash = float(cash)
        except:
            return apology("Deposit amount must be a positive integer", 400)

        if not cash % 1 == 0 or not cash > 0:
            return apology("Deposit amount must be a positive integer", 400)

        # Query the user's cash
        previous_cash = db.execute("SELECT cash FROM users WHERE id=?", session['user_id'])[0]['cash']

        updated_cash = previous_cash + cash

        db.execute("UPDATE users SET cash=? WHERE id=?", updated_cash, session['user_id'])

        return redirect("/")

    return render_template("/deposit.html")