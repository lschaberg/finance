from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
from datetime import datetime
import os
import psycopg2

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL(os.environ.get("DATABASE_URL") or "sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT symbol, SUM(shares) AS shares FROM trades WHERE user_id = :id GROUP BY symbol HAVING SUM(shares) > 0", id = session["user_id"])
    titles = ["Symbol", "Name", "Shares", "Price", "TOTAL"]
    tablerows = []
    cash = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])[0]["cash"]
    assetvalue = cash
    print(rows)
    for i in range(0, len(rows)):
        stock = lookup(rows[i]["symbol"])
        assetvalue += stock["price"]*int(rows[i]["shares"])
        tablerows.append([rows[i]["symbol"], stock["name"], rows[i]["shares"], usd(stock["price"]), usd(int(rows[i]["shares"])*float(stock["price"]))])
    return render_template("index.html", titles = titles, tablerows = tablerows, cash = usd(cash), assetvalue = usd(assetvalue))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "POST":
        rows = lookup(request.form.get("symbol"))
        if rows is None:
            return apology("invalid symbol")
           
        try:
            int(request.form.get("shares"))
        except ValueError:
            return apology("invalid number of shares")
        if int(request.form.get("shares")) < 0:
            return apology("invalid number of shares")
            
        xdict = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
        if rows["price"]*int(request.form.get("shares")) > xdict[0]["cash"]:
            return apology("can't afford")
    
        db.execute("INSERT INTO trades (user,symbol,price,shares,datetime) VALUES (:user,:symbol,:price,:shares,:datetime)", user = session["user_id"], symbol = rows["symbol"], price = rows["price"], shares = request.form.get("shares"), datetime = datetime.utcnow().isoformat(" "))
        db.execute("UPDATE users SET cash = cash-:spent WHERE id = :id", spent = rows["price"]*int(request.form.get("shares")), id = session["user_id"])
        return redirect(url_for("index"))
        
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    rows = db.execute("SELECT * FROM trades WHERE user_id = :id", id = session["user_id"])
    titles = ["Symbol", "Shares", "Price", "Transacted"]
    tablerows = []
    for i in range(0, len(rows)):
        tablerows.append([rows[i]["symbol"], rows[i]["shares"], usd(rows[i]["price"]), rows[i]["datetime"]])
    return render_template("history.html", titles = titles, tablerows = tablerows)
    
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        rows = lookup(request.form.get("symbol"))
        if rows is None:
            return apology("invalid symbol")
        
        rows["price"] = usd(rows["price"])
        return render_template("quoted.html", quote=rows)
        
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    session.clear()
    """Register user."""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username")
            
        # query database for username
        elif len(db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))) != 0:
            return apology("username already in use")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure password was confirmed
        elif not request.form.get("confirmpassword"):
            return apology("must confirm password")
        
        #ensure passwords match
        elif request.form.get("confirmpassword") != request.form.get("password"):
            return apology("passwords must match")

        # enter user into database
        db.execute("INSERT INTO users (username,hash) VALUES (:username,:hash)", username=request.form["username"], hash=pwd_context.hash(request.form["password"]))
        return redirect(url_for("index"))
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        rows = lookup(request.form.get("symbol"))
        if rows is None:
            return apology("invalid symbol")
            
        try:
            int(request.form.get("shares"))
        except ValueError:
            return apology("invalid number of shares")
        if int(request.form.get("shares")) < 0:
            return apology("invalid number of shares")

           
        totalshares = db.execute("SELECT SUM(shares) AS shares FROM trades WHERE user_id = :id AND symbol = :symbol", id = session["user_id"], symbol = rows["symbol"])
        if int(request.form.get("shares")) > int(totalshares[0]["shares"]):
            return apology("not enough shares")
    
        db.execute("INSERT INTO trades (user_id,symbol,price,shares,datetime) VALUES (:user,:symbol,:price,:shares,:datetime)", user = session["user_id"], symbol = rows["symbol"], price = rows["price"], shares = -int(request.form.get("shares")), datetime = datetime.utcnow().isoformat(" "))
        db.execute("UPDATE users SET cash = cash+:earned WHERE id = :id", earned = rows["price"]*int(request.form.get("shares")), id = session["user_id"])
        return redirect(url_for("index"))
        
    else:
        return render_template("sell.html")
        
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)