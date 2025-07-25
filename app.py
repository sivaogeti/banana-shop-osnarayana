# app.py

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from io import BytesIO
from fpdf import FPDF
import plotly.express as px
from gupshup_sender import send_gupshup_whatsapp
from textwrap import dedent

SALES_FILE = "sales.csv"
PAYMENTS_FILE = "payments.csv"
USERS_FILE = "users.json"
COMMISSION_PER_BUNCH = 20

# Known customers map
CUSTOMER_WHATSAPP_MAP = {
    "os1": "+919008030624",
    "badri": "+917989502014",
    "os2": "+919848228523"
}

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def authenticate(username, password, users):
    return username in users and users[username] == password

def initialize_file(file_path, columns):
    if not os.path.exists(file_path):
        pd.DataFrame(columns=columns).to_csv(file_path, index=False)

def clean_csv(file_path, expected_columns):
    try:
        df = pd.read_csv(file_path)
        df = df[[col for col in expected_columns if col in df.columns]]
        df.to_csv(file_path, index=False)
    except:
        initialize_file(file_path, expected_columns)

def load_sales_table():
    clean_csv(SALES_FILE, ["date", "name", "bunches", "total"])
    df = pd.read_csv(SALES_FILE)
    if df.empty: return df
    df["bunches"] = pd.to_numeric(df["bunches"], errors="coerce").fillna(0)
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df["Commission"] = df["bunches"] * COMMISSION_PER_BUNCH
    df["Final Amount"] = df["total"] - df["Commission"]
    return df

def load_payments():
    clean_csv(PAYMENTS_FILE, ["name", "date", "paid_amount"])
    df = pd.read_csv(PAYMENTS_FILE)
    df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0)
    return df

def delete_payment(index_to_delete):
    df = pd.read_csv(PAYMENTS_FILE)
    df.drop(index=index_to_delete, inplace=True)
    df.to_csv(PAYMENTS_FILE, index=False)

def generate_customer_summary(df):
    if df.empty: return pd.DataFrame(), pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y")
    df.sort_values(by=["name", "date"], inplace=True)
    total_summary = df.groupby("name")["Final Amount"].sum().reset_index()
    total_summary.columns = ["name", "Total Amount"]
    return df, total_summary

def generate_payment_tracking(total_summary, payments):
    if total_summary.empty: return pd.DataFrame()
    logs = payments.copy()
    logs["paid_amount"] = pd.to_numeric(logs["paid_amount"], errors="coerce").fillna(0)
    logs["date"] = pd.to_datetime(logs["date"], format="%d-%b-%Y")
    logs["row_index"] = logs.index
    logs = logs.sort_values(by=["name", "date", "row_index"]).reset_index(drop=True)
    logs["Total Paid"] = 0
    logs["Remaining"] = 0

    for cust in logs["name"].unique():
        cust_mask = logs["name"] == cust
        cust_df = logs.loc[cust_mask].copy()
        cust_df["Total Paid"] = cust_df["paid_amount"].cumsum()
        total_amt = total_summary.loc[total_summary["name"] == cust, "Total Amount"].values[0]
        cust_df["Remaining"] = total_amt - cust_df["Total Paid"]
        logs.loc[cust_mask, ["Total Paid", "Remaining"]] = cust_df[["Total Paid", "Remaining"]]

    logs = logs.sort_values(by="row_index", ascending=False).reset_index(drop=True)
    logs["date"] = logs["date"].dt.strftime("%d-%b-%Y")
    return logs

def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    col_width = pdf.w / (len(df.columns) + 1)
    for col in df.columns:
        pdf.cell(col_width, 10, str(col), border=1)
    pdf.ln()
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(col_width, 10, str(item), border=1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def dashboard():
    with st.sidebar:
        st.write(f"👤 `{st.session_state.username}`")
        if st.button("🔓 Logout"): st.session_state.logged_in = False; st.rerun()
        if st.button("🗑 Reset Data"):
            initialize_file(SALES_FILE, ["date", "name", "bunches", "total"])
            initialize_file(PAYMENTS_FILE, ["name", "date", "paid_amount"])
            st.success("✅ Data reset!"); st.rerun()
        st.radio("📊 Chart Type", ["None", "Bar", "Line", "Pie"], key="chart_type")

    st.title("🍌 M R Banana Business App")
    df_sales = load_sales_table()
    df_payments = load_payments()
    per_entry_summary, total_summary = generate_customer_summary(df_sales)

    st.subheader("📥 Enter Sale")
    with st.form("sale_form"):
        date = st.date_input("Date", datetime.today())
        name = st.text_input("Customer Name")
        bunches = st.number_input("Bunches", min_value=1)
        total = st.number_input("Total ₹", min_value=1)
        submit = st.form_submit_button("Add Sale")
    if submit:
        add_sale_entry(date.strftime("%d-%b-%Y"), name, bunches, total)
        st.session_state.last_customer = name
        st.success("✅ Sale added!"); st.rerun()

    st.subheader("📊 Sales Summary")
    if not df_sales.empty:
        names = sorted(per_entry_summary["name"].dropna().unique())
        default_idx = names.index(st.session_state.get("last_customer", names[0])) if "last_customer" in st.session_state else 0
        selected = st.selectbox("Filter Customer", ["All"] + names, index=default_idx + 1)
        filtered = df_sales if selected == "All" else df_sales[df_sales["name"] == selected]
        st.dataframe(filtered, use_container_width=True)

        pdf_bytes = generate_pdf(filtered)
        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button("⬇️ Download PDF", pdf_bytes, file_name="sales_summary.pdf")

        with col2:
            to_number = CUSTOMER_WHATSAPP_MAP.get(selected, "")
            if not to_number and selected != "All":
                to_number = st.text_input(f"📱 Enter WhatsApp Number for {selected}", value="+91", key="sales_whatsapp_number")
            if st.button("📤 Send WhatsApp"):
                if selected == "All":
                    st.warning("⚠️ Please select a specific customer.")
                elif not to_number or to_number.strip() == "+91":
                    st.warning("⚠️ Please enter a valid WhatsApp number.")
                elif not filtered.empty:
                    summary_lines = [
                        f"📊 Sales Summary for {selected}",
                        f"{'Date':<12} {'Bunches':>8} {'Total':>10} {'Commission':>12} {'Final':>10}",
                        "-" * 60
                    ]
                    for _, row in filtered.iterrows():
                        summary_lines.append(
                            f"{row['date']:<12} {int(row['bunches']):>8} ₹{int(row['total']):>9} ₹{int(row['Commission']):>11} ₹{int(row['Final Amount']):>9}"
                        )
                    summary_text = "\n".join(summary_lines)
                    send_gupshup_whatsapp(selected, summary_text, fallback_number=to_number)
                    st.success(f"✅ Sent to {to_number}")
                else:
                    st.warning("⚠️ No sales data to send.")

    if st.session_state.chart_type != "None" and not df_sales.empty:
        chart = df_sales.groupby("name")["Final Amount"].sum().reset_index()
        if st.session_state.chart_type == "Line":
            chart = df_sales.groupby("date")["Final Amount"].sum().reset_index()
            fig = px.line(chart, x="date", y="Final Amount")
        elif st.session_state.chart_type == "Bar":
            fig = px.bar(chart, x="name", y="Final Amount")
        elif st.session_state.chart_type == "Pie":
            fig = px.pie(chart, names="name", values="Final Amount")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("💰 Payment Tracker")
    with st.form("payment_form"):
        names = sorted(total_summary["name"].dropna().unique())
        default_idx = names.index(st.session_state.get("last_customer", names[0])) if names else 0
        pay_name = st.selectbox("Customer Name", names, index=default_idx)
        pay_date = st.date_input("Payment Date", datetime.today())
        pay_amount = st.number_input("Paid Amount", min_value=1)
        pay_submit = st.form_submit_button("Record Payment")
    if pay_submit:
        add_payment_entry(pay_name, pay_date.strftime("%d-%b-%Y"), pay_amount)
        st.session_state.last_customer = pay_name
        st.success("✅ Payment recorded!"); st.rerun()

    payment_table = generate_payment_tracking(total_summary, df_payments)
    if not payment_table.empty:
        selected_name = st.selectbox("View Payments for", ["All"] + names, index=(names.index(st.session_state.get("last_customer")) + 1 if "last_customer" in st.session_state else 0))
        filtered = payment_table if selected_name == "All" else payment_table[payment_table["name"] == selected_name]
        st.dataframe(filtered, use_container_width=True)

        if selected_name != "All" and not filtered.empty:
            st.markdown(f"**Summary:** Total Paid ₹{filtered['paid_amount'].sum()} | Remaining ₹{filtered['Remaining'].iloc[-1]}")

        pdf_bytes = generate_pdf(filtered)
        col3, col4, col5, col6 = st.columns(4)

        with col3:
            st.download_button("⬇️ PDF", pdf_bytes, file_name="payment_tracker.pdf")

        with col4:
            if selected_name != "All":
                to_number = CUSTOMER_WHATSAPP_MAP.get(selected_name, "")
                if not to_number:
                    to_number = st.text_input(f"📱 Enter WhatsApp Number for {selected_name}", value="+91", key="payment_whatsapp_number")
                if st.button("📤 WhatsApp Payment"):
                    if not filtered.empty and to_number and to_number != "+91":
                        summary_lines = [
                            f"💰 Payment Summary for {selected_name}",
                            f"{'Date':<12} {'Paid':>6} {'Total Paid':>12} {'Remaining':>12}",
                            "-" * 44
                        ]
                        for row in filtered.to_dict(orient="records"):
                            summary_lines.append(f"{row['date']:<12} ₹{int(row['paid_amount']):>6} ₹{int(row['Total Paid']):>12} ₹{int(row['Remaining']):>12}")
                        send_gupshup_whatsapp(selected_name, "\n".join(summary_lines), fallback_number=to_number)
                        st.success(f"✅ Sent to {to_number}")
                    else:
                        st.warning("⚠️ No payments or number invalid.")

        with col5:
            if not filtered.empty:
                delete_idx = st.number_input("Delete row index", min_value=0, max_value=len(filtered) - 1, step=1)
                if st.button("❌ Delete Payment"):
                    delete_payment(filtered.index[delete_idx])
                    st.success("✅ Deleted"); st.rerun()
            else:
                st.warning("⚠️ No records to delete.")

def add_sale_entry(date, name, bunches, total):
    df = pd.read_csv(SALES_FILE)
    new_row = {"date": date, "name": name, "bunches": bunches, "total": total}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(SALES_FILE, index=False)

def add_payment_entry(name, date, amount):
    df = pd.read_csv(PAYMENTS_FILE)
    new_row = {"name": name, "date": date, "paid_amount": amount}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PAYMENTS_FILE, index=False)

def main():
    st.set_page_config(page_title="Banana Tracker", layout="wide")
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in:
        dashboard()
    else:
        st.subheader("🔐 Login")
        with st.form("login_form"):
            username = st.text_input("Name")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted and authenticate(username, password, load_users()):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error("❌ Invalid credentials")

if __name__ == "__main__":
    main()
