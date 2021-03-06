# import sqlite3
import base64
import os
from collections import deque
from datetime import timedelta
from functools import lru_cache
from io import BytesIO

import joblib
import matplotlib.pyplot as plt
import pandas as pd
from bitcoin_forecast.scrap_data import get_today_data
from flask import Flask, render_template

from retrain_scheduler import run_scheduler

app = Flask(__name__)
model = joblib.load("rls_model.joblib")
model_cols = joblib.load("model_cols.joblib")

# start scheduler to re-train model for every 20 days
run_scheduler()


@app.route("/")
def home():
    return render_template("index.html")


@lru_cache
def get_and_store_data():
    data = get_today_data()
    # Create your connection.
    # with sqlite3.connect("bitcoin_db") as cnx:
    #     data.to_sql(name="bitcoin_data", con=cnx, if_exists="append")
    return data


# @lru_cache
def get_comparison_data(t, t1):
    path = "table/"
    os.makedirs(path, exist_ok=True)
    if len(os.listdir(path)) == 0:
        t_dates = deque(maxlen=5)
        t1_dates = deque(maxlen=6)
        t_dates.appendleft(list(t.keys())[0])
        t1_dates.appendleft(list(t1.keys())[0])
        final_dict = {"Predicted": t1, "Actual": t}
    else:
        final_dict = joblib.load(path + "comp.joblib")
        t_dates = joblib.load(path + "t_dates.joblib")
        t1_dates = joblib.load(path + "t1_dates.joblib")

        if not (list(t.keys())[0] in t_dates):
            t_dates.appendleft(list(t.keys())[0])

        if not (list(t1.keys())[0] in t1_dates):
            t1_dates.appendleft(list(t1.keys())[0])

        final_dict["Predicted"].update(t1)
        final_dict["Actual"].update(t)

    # storing only last 7 dates data
    final_dict["Predicted"] = {date: final_dict["Predicted"][date] for date in t1_dates}
    final_dict["Actual"] = {date: final_dict["Actual"][date] for date in t_dates}

    joblib.dump(final_dict, path + "comp.joblib")
    joblib.dump(t_dates, path + "t_dates.joblib")
    joblib.dump(t1_dates, path + "t1_dates.joblib")
    return final_dict


@app.route("/predict", methods=["POST"])
def predict():
    """
    For rendering results on HTML GUI
    """
    today_df = get_and_store_data()
    # joblib.dump(today_df, "temp.jlb")
    # today_df = joblib.load("temp.jlb")
    # get_data.cache_clear() # TODO: clear cache every day
    price = model.predict(today_df[model_cols])[0]
    usd = today_df["price_usd"].values[0]
    today_date = today_df["Date"]
    today_price = today_df["price_btc"]
    tomorrow_date = (today_date + timedelta(1)).dt.strftime("%d-%b-%Y")[0]
    today = {today_date.dt.strftime("%d-%b-%Y")[0]: today_price[0]}
    tomorrow = {tomorrow_date: price}
    # today = {'26-Jan-2022': 43783.58}
    # tomorrow = {'27-Jan-2022': 43783.58}
    json_table = get_comparison_data(today, tomorrow)
    df = pd.DataFrame(json_table)
    df.index = pd.to_datetime(df.index)
    df = df.loc[
        df.index.sort_values(ascending=False),
    ].copy()
    html_table = df.fillna("-").to_html(
        table_id="comparison_table", classes=["table", "table-bordered", "table-condensed"], border=0
    )

    graph = create_fig(df)
    return render_template(
        "index.html",
        prediction_text=f"Bitcoin price $ {price:.2f} USD ({price * usd:.2f} INR) on {tomorrow_date}",
        comparison_table=html_table,
        image=graph.decode("utf8"),
    )


def create_fig(df):
    df = df.fillna(0.0)
    figfile = BytesIO()
    fig, ax = plt.subplots(figsize=(8, 3))
    df = df[::-1]
    # print(df)
    df.index = df.index.strftime("%d-%b-%Y")
    # plot = df.plot(title="Actual vs Predicted price (USD)", figsize=(8, 3), ax=ax)
    # plot.set_xticks(range(len(df)))
    # plot.set_xticklabels(df.index)
    ax.plot(df.index, df["Actual"], label="Actual")
    ax.plot(df.index, df["Predicted"], label="Predicted")
    ax.legend()
    ax.set_title("Actual vs Predicted price (USD)")
    ax.set_xlabel("year")
    ax.set_ylabel("price (USD)")
    fig.subplots_adjust(bottom=0.2)
    fig = fig.get_figure()
    fig.savefig(figfile, format="png")
    figfile.seek(0)
    figdata_png = base64.b64encode(figfile.getvalue())
    return figdata_png


if __name__ == "__main__":

    app.run(debug=True)
