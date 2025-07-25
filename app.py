# Fixed and enhanced app.py with:
# - Login UI retained
# - Sidebar (Logout, Delete, Chart select) present
# - Fixes for payment sort/calc
# - Payment delete, balance summary, WhatsApp+Email support
# - Per-customer export (PDF/WhatsApp/Email)

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from io import BytesIO
from fpdf import FPDF
import plotly.express as px
from whatsapp_sender import send_whatsapp, send_whatsapp_with_pdf
from gupshup_sender import send_gupshup_whatsapp
from textwrap import dedent

#--------------Sending payment summary in formatted way----------------
def format_payment_summary_text(name, df):
    if df.empty:
        return f"No payment records found for {name}."

    header = f"\n💰 Payment Summary for {name}\n"
    table_header = f"{'Date':<13} {'Paid':<7} {'Total Paid':<12} {'Remaining':<10}"
    separator = "-" * len(table_header)
    rows = []

    for _, row in df.iterrows():
        date = row["date"]
        paid = f"₹{int(row['paid_amount'])}" if row['paid_amount'] else "-"
        total_paid = f"₹{int(row['Total Paid'])}" if row['Total Paid'] else "-"
        remaining = f"₹{row['Remaining']:,}" if row['Remaining'] else "-"
        row_text = f"{date:<13} {paid:<7} {total_paid:<12} {remaining:<10}"
        rows.append(row_text)

    return f"{header}{table_header}\n{separator}\n" + "\n".join(rows)


#from send_email import send_email

SALES_FILE = "sales.csv"
PAYMENTS_FILE = "payments.csv"
USERS_FILE = "users.json"
COMMISSION_PER_BUNCH = 20

# Customer-to-WhatsApp number mapping (for known users)
CUSTOMER_WHATSAPP_MAP = {
    "os1": "+919008030624",
    "badri": "+917989502014",
    "os2":  "+919848228523"
    # Add more known customers here
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
    if df.empty:
        return df
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
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    summary = df.copy()
    summary["date"] = pd.to_datetime(summary["date"], format="%d-%b-%Y")
    summary.sort_values(by=["name", "date"], inplace=True)
    total_summary = summary.groupby("name")["Final Amount"].sum().reset_index()
    total_summary.columns = ["name", "Total Amount"]
    return summary, total_summary

def generate_payment_tracking(total_summary, payments):
    if total_summary.empty:
        return pd.DataFrame()

    payment_logs = payments.copy()
    payment_logs["paid_amount"] = pd.to_numeric(payment_logs["paid_amount"], errors="coerce").fillna(0)
    payment_logs["date"] = pd.to_datetime(payment_logs["date"], format="%d-%b-%Y")
    
    # Preserve original row order for later
    payment_logs["row_index"] = payment_logs.index

    # First sort for accurate cumulative calculation
    payment_logs = payment_logs.sort_values(by=["name", "date", "row_index"]).reset_index(drop=True)

    payment_logs["Total Paid"] = 0
    payment_logs["Remaining"] = 0

    for cust in payment_logs["name"].unique():
        cust_mask = payment_logs["name"] == cust
        cust_df = payment_logs.loc[cust_mask].copy()
        cust_df["Total Paid"] = cust_df["paid_amount"].cumsum()
        total_amt = total_summary.loc[total_summary["name"] == cust, "Total Amount"].values[0]
        cust_df["Remaining"] = total_amt - cust_df["Total Paid"]
        payment_logs.loc[cust_mask, ["Total Paid", "Remaining"]] = cust_df[["Total Paid", "Remaining"]]

    # Sort by original row index descending (latest at top)
    payment_logs = payment_logs.sort_values(by="row_index", ascending=False).reset_index(drop=True)
    payment_logs["date"] = payment_logs["date"].dt.strftime("%d-%b-%Y")

    return payment_logs


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
            st.success("✅ Data reset!")
            st.rerun()
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
        st.success("✅ Sale added!")
        st.rerun()

    st.subheader("📊 Sales Summary")
    if not df_sales.empty:
        names = sorted(per_entry_summary["name"].dropna().unique())
        default_idx = 0 if "last_customer" not in st.session_state else names.index(st.session_state.last_customer)
        selected = st.selectbox("Filter Customer", ["All"] + names, index=default_idx+1)
        filtered = df_sales if selected == "All" else df_sales[df_sales["name"] == selected]
        st.dataframe(filtered, use_container_width=True)

        pdf_bytes = generate_pdf(filtered)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button("⬇️ Download PDF", pdf_bytes, file_name="sales_summary.pdf")
        with col2:
            if st.button("📤 Send WhatsApp"):
                filename = f"sales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                pdf_bytes = generate_pdf(filtered)
                #send_whatsapp_with_pdf("📊 Sales Report", pdf_bytes, filename, to_number="+919008030624")
                message = "💰 Your payment summary is ready. Please refer to the app for full report."
                send_gupshup_whatsapp(selected_name, message, fallback_number="+919008030624")
                st.success("✅ Sent")

        with col3:
            if st.button("📧 Send Email"):
                send_email("Sales Report", "See attached PDF", "test@example.com", pdf_bytes)
                st.success("✅ Sent")

    if st.session_state.chart_type != "None" and not df_sales.empty:
        chart = df_sales.groupby("name")["Final Amount"].sum().reset_index()
        fig = None
        if st.session_state.chart_type == "Bar":
            fig = px.bar(chart, x="name", y="Final Amount")
        elif st.session_state.chart_type == "Line":
            chart = df_sales.groupby("date")["Final Amount"].sum().reset_index()
            fig = px.line(chart, x="date", y="Final Amount")
        elif st.session_state.chart_type == "Pie":
            fig = px.pie(chart, names="name", values="Final Amount")
        if fig: st.plotly_chart(fig, use_container_width=True)

    st.subheader("💰 Payment Tracker")
    with st.form("payment_form"):
        names = sorted(total_summary["name"].dropna().unique())
        default_idx = names.index(st.session_state.get("last_customer", names[0])) if names else 0
        pay_name = st.selectbox("Customer Name", names, index=default_idx)
        pay_date = st.date_input("Payment Date", value=datetime.today())
        pay_amount = st.number_input("Paid Amount", min_value=1)
        pay_submit = st.form_submit_button("Record Payment")
    if pay_submit:
        add_payment_entry(pay_name, pay_date.strftime("%d-%b-%Y"), pay_amount)
        st.session_state.last_customer = pay_name
        st.success("✅ Payment recorded!")
        st.rerun()

    payment_table = generate_payment_tracking(total_summary, df_payments)
    if not payment_table.empty:
        selected_name = st.selectbox("View Payments for", ["All"] + names, index=(names.index(st.session_state.get("last_customer")) + 1 if "last_customer" in st.session_state else 0))
        filtered = payment_table if selected_name == "All" else payment_table[payment_table["name"] == selected_name]
        st.dataframe(filtered, use_container_width=True)

        # Summary row
        if selected_name != "All" and not filtered.empty:
            total_paid = filtered["paid_amount"].sum()
            remaining = filtered["Remaining"].iloc[-1]
            st.markdown(f"**Summary:** Total Paid ₹{total_paid} | Remaining ₹{remaining}")

        pdf_bytes = generate_pdf(filtered)
        col4, col5, col6, col7 = st.columns(4)
        with col4:
            st.download_button("⬇️ PDF", pdf_bytes, file_name="payment_tracker.pdf")
        with col5:
            if selected_name != "All":
                mapped_number = CUSTOMER_WHATSAPP_MAP.get(selected_name, "")
                to_number = mapped_number

                if not mapped_number:
                    to_number = st.text_input(f"📱 Enter WhatsApp Number for {selected_name}", value="+91")

                if st.button("📤 WhatsApp Payment"):
                    if not filtered.empty:
                        payment_rows = filtered.to_dict(orient="records")
                
                        # Header and table title
                        summary_lines = [
                            f"💰 Payment Summary for {selected_name}",
                            f"{'Date':<12} {'Paid':>6} {'Total Paid':>12} {'Remaining':>12}",
                            "-" * 44
                        ]
                
                        # Format rows with padding
                        for row in payment_rows:
                            date = row['date']
                            paid = f"₹{int(row['paid_amount'])}"
                            total_paid = f"₹{int(row['Total Paid'])}"
                            remaining = f"₹{int(row['Remaining']):,}"
                
                            summary_lines.append(
                                f"{date:<12} {paid:>6} {total_paid:>12} {remaining:>12}"
                            )
                
                        summary_text = "\n".join(summary_lines)
                        send_gupshup_whatsapp(selected_name, summary_text, fallback_number=to_number)
                        st.success(f"✅ Sent to {to_number}")
                    else:
                        st.warning("⚠️ No payments to send for selected customer.")


        with col6:
            if st.button("📧 Email Payment"):
                send_email("Payment Report", "See attached", "test@example.com", pdf_bytes)
                st.success("✅ Sent")
        with col7:
            delete_idx = st.number_input("Delete row index", min_value=0, max_value=len(filtered)-1, step=1)
            if st.button("❌ Delete Payment"):
                delete_payment(filtered.index[delete_idx])
                st.success("✅ Deleted")
                st.rerun()

def add_sale_entry(date, name, bunches, total):
    df = pd.read_csv(SALES_FILE)
    df = pd.concat([df, pd.DataFrame([{ "date": date, "name": name, "bunches": bunches, "total": total }])], ignore_index=True)
    df.to_csv(SALES_FILE, index=False)

def add_payment_entry(name, date, amount):
    df = pd.read_csv(PAYMENTS_FILE)
    df = pd.concat([df, pd.DataFrame([{ "name": name, "date": date, "paid_amount": amount }])], ignore_index=True)
    df.to_csv(PAYMENTS_FILE, index=False)

def main():
    st.set_page_config(page_title="Banana Tracker", layout="wide")
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if st.session_state.logged_in:
        dashboard()
    else:
        st.subheader("🔐 Login")
        with st.form("login_form"):
            username = st.text_input("Name")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            if authenticate(username, password, load_users()):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("❌ Invalid credentials")

if __name__ == "__main__":
    main()
