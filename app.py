# Banana Tracker - Final Enhanced app.py with Persistent Discounts

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from io import BytesIO
from fpdf import FPDF
import plotly.express as px
from gupshup_sender import send_gupshup_whatsapp

SALES_FILE = "sales.csv"
PAYMENTS_FILE = "payments.csv"
USERS_FILE = "users.json"
COMMISSION_PER_BUNCH = 20
SESSION_TIMEOUT_MINUTES = 15

CUSTOMER_WHATSAPP_MAP = {
    "os1": "+919008030624",
    "badri": "+917989502914",
    "os2": "+919848228523"
}


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
            return users
    except Exception as e:
        print("❌ JSON Load Error:", e)
        return {}

def authenticate(username, password, users):
    username = username.strip()
    password = password.strip()
    if username in users:
        return users[username]["password"] == password
    return False

def is_admin(username):
    users = load_users()
    return users.get(username, {}).get("role") == "admin"

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
    df = df[::-1].reset_index(drop=True)
    return df

def load_payments():
    clean_csv(PAYMENTS_FILE, ["name", "date", "paid_amount", "discount"])
    df = pd.read_csv(PAYMENTS_FILE)
    df["paid_amount"] = pd.to_numeric(df["paid_amount"], errors="coerce").fillna(0)
    if "discount" not in df.columns:
        df["discount"] = 0
    else:
        df["discount"] = pd.to_numeric(df["discount"], errors="coerce").fillna(0)
    return df

def add_sale_entry(date, name, bunches, total):
    df = pd.read_csv(SALES_FILE)
    new_row = {"date": date, "name": name, "bunches": bunches, "total": total}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(SALES_FILE, index=False)

def add_payment_entry(name, date, amount, discount=0):
    df = pd.read_csv(PAYMENTS_FILE)
    new_row = {"name": name, "date": date, "paid_amount": amount, "discount": discount}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PAYMENTS_FILE, index=False)

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

def generate_payment_tracking(total_summary, payments, discount_map):
    if total_summary.empty: return pd.DataFrame()

    logs = payments.copy()
    logs["paid_amount"] = pd.to_numeric(logs["paid_amount"], errors="coerce").fillna(0)
    logs["discount"] = pd.to_numeric(logs["discount"], errors="coerce").fillna(0)
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
        cust_df["Remaining"] = total_amt - (cust_df["Total Paid"] + cust_df["discount"].cumsum())
        logs.loc[cust_mask, ["Total Paid", "Remaining"]] = cust_df[["Total Paid", "Remaining"]]

    logs = logs.sort_values(by="row_index", ascending=False).reset_index(drop=True)
    logs["date"] = logs["date"].dt.strftime("%d-%b-%Y")
    logs.rename(columns={"discount": "Discount"}, inplace=True)
    return logs

def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    col_width = pdf.w / (len(df.columns) + 1)
    for col in df.columns:
        if col != "row_index":
            pdf.cell(col_width, 10, str(col), border=1)
    pdf.ln()
    for _, row in df.iterrows():
        for k, v in row.items():
            if k != "row_index":
                pdf.cell(col_width, 10, str(v), border=1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def generate_excel(df):
    df = df.drop(columns=["row_index"], errors="ignore")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()

def add_sale_entry(date, name, bunches, total):
    df = pd.read_csv(SALES_FILE)
    new_row = {"date": date, "name": name, "bunches": bunches, "total": total}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(SALES_FILE, index=False)

def add_payment_entry(name, date, amount, discount=0):
    df = pd.read_csv(PAYMENTS_FILE)
    new_row = {"name": name, "date": date, "paid_amount": amount, "discount": discount}
    pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PAYMENTS_FILE, index=False)

def check_session_timeout():
    if "login_time" in st.session_state:
        if datetime.now() - st.session_state.login_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            st.warning("⏳ Session expired. Please log in again.")
            st.session_state.logged_in = False
            st.rerun()

def dashboard():
    check_session_timeout()
    with st.sidebar:
        st.write(f"👤 `{st.session_state.username}`")
        if st.button("🔓 Logout"):
            st.session_state.logged_in = False
            st.rerun()
        if st.button("🗑 Reset Data"):
            initialize_file(SALES_FILE, ["date", "name", "bunches", "total"])
            initialize_file(PAYMENTS_FILE, ["name", "date", "paid_amount"])
            st.success("✅ Data reset!"); st.rerun()
        st.radio("📊 Chart Type", ["None", "Bar", "Line", "Pie"], key="chart_type")

    st.title("🍌 M R Banana Business App")
    df_sales = load_sales_table()
    df_payments = load_payments()
    per_entry_summary, total_summary = generate_customer_summary(df_sales)

    discount_map = {}
    
    pay_discount = 0
    if is_admin(st.session_state.username):
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
        #default_idx = names.index(st.session_state.get("last_customer", names[0])) if "last_customer" in st.session_state else 0
        default_idx = 0
        if "last_customer" in st.session_state and st.session_state.last_customer in names:
            default_idx = names.index(st.session_state.last_customer)
        selected = st.selectbox("Filter Customer", ["All"] + names, index=default_idx + 1)
        filtered = df_sales if selected == "All" else df_sales[df_sales["name"] == selected]
        st.dataframe(filtered, use_container_width=True)

        pdf_bytes = generate_pdf(filtered)
        excel_bytes = generate_excel(filtered)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button("⬇️ PDF", pdf_bytes, file_name="sales_summary.pdf")
        with col2:
            st.download_button("⬇️ Excel", excel_bytes, file_name="sales_summary.xlsx")
        with col3:
            to_number = CUSTOMER_WHATSAPP_MAP.get(selected, "")
            if not to_number and selected != "All":
                to_number = st.text_input(f"📱 Enter WhatsApp Number for {selected}", value="+91", key="sales_whatsapp_number")
            if st.button("📤 Send WhatsApp"):
                if selected == "All":
                    st.warning("⚠️ Please select a specific customer.")
                elif not to_number or to_number.strip() == "+91":
                    st.warning("⚠️ Please enter a valid WhatsApp number.")
                elif not filtered.empty:
                    if not filtered.empty:
                        filtered["date"] = pd.to_datetime(filtered["date"]).dt.strftime("%d-%b-%Y")  # ✅ Fix here for showing wrong value in whatsapped message
                    summary_lines = [
                        f"📊 Sales Summary for {selected}",
                        f"{'  Date  ':<12} {'  Bunches  ':>8} {'  Total  ':>10} {'  Commission  ':>12} {'  Final  ':>10}",
                        "-" * 60
                    ]
                    for _, row in filtered.iterrows():
                        summary_lines.append(
                            f"{row['date']:<12} {int(row['bunches']):>8} ₹{int(row['total']):>9} ₹{int(row['Commission']):>11} ₹{int(row['Final Amount']):>9}"
                        )
                    send_gupshup_whatsapp(selected, "\n".join(summary_lines), fallback_number=to_number)
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
        #default_idx = names.index(st.session_state.get("last_customer", names[0])) if names else 0
        default_idx = 0
        if "last_customer" in st.session_state and st.session_state.last_customer in names:
            default_idx = names.index(st.session_state.last_customer)
        pay_name = st.selectbox("Customer Name", names, index=default_idx)
        pay_date = st.date_input("Payment Date", datetime.today())
        pay_amount = st.number_input("Paid Amount", min_value=1)
        pay_submit = st.form_submit_button("Record Payment")
    if pay_submit:
        add_payment_entry(pay_name, pay_date.strftime("%d-%b-%Y"), pay_amount)
        st.session_state.last_customer = pay_name
        st.success("✅ Payment recorded!"); st.rerun()

    st.subheader("📊 Payment Summary")
    #selected_name = st.selectbox("View Payments for", ["All"] + names, index=(names.index(st.session_state.get("last_customer")) + 1 if "last_customer" in st.session_state else 0))
    selected_name = "All"
    if names:
        selected_idx = 0
        if "last_customer" in st.session_state and st.session_state.last_customer in names:
            selected_idx = names.index(st.session_state.last_customer)
        selected_name = st.selectbox("View Payments for", ["All"] + names, index=selected_idx + 1)
    else:
        st.info("ℹ️ No customers to show in payments.")


    
    apply_discount = False
    discount_amount = 0
    if selected_name != "All" and is_admin(st.session_state.username):
        apply_discount = st.checkbox(f"🎁 Apply final discount for {selected_name}?", value=False)
        if apply_discount:
            discount_amount = st.number_input("Enter Discount Amount ₹", min_value=0)
            discount_map[selected_name] = discount_amount

            # Save the discount as a payment row with ₹0 amount if not already present today
            today_str = datetime.today().strftime("%d-%b-%Y")
            today_entries = df_payments[
                (df_payments["name"] == selected_name) & 
                (df_payments["date"] == today_str) & 
                (df_payments["paid_amount"] == 0) & 
                (df_payments["discount"] == discount_amount)
            ]
            if today_entries.empty:
                add_payment_entry(selected_name, today_str, 0, discount_amount)
                st.success(f"✅ Discount ₹{discount_amount} recorded for {selected_name}")
                st.rerun()


    payment_table = generate_payment_tracking(total_summary, df_payments, discount_map)
    filtered = payment_table if selected_name == "All" else payment_table[payment_table["name"] == selected_name]
    st.dataframe(filtered.drop(columns=["row_index"]), use_container_width=True)

    if selected_name != "All" and not filtered.empty:        
        remaining = filtered["Remaining"].iloc[0]  # Latest row after descending sort
        total_paid = filtered["paid_amount"].sum()
        total_discount = discount_map.get(selected_name, 0)
        st.markdown(
            f"**Summary:** Total Paid ₹{total_paid} | Discount ₹{total_discount} | Final Remaining ₹{remaining}"
        )

    pdf_bytes = generate_pdf(filtered)
    excel_bytes = generate_excel(filtered)

    col3, col4, col5 = st.columns(3)
    with col3:
        st.download_button("⬇️ PDF", pdf_bytes, file_name="payment_tracker.pdf")
    with col4:
        st.download_button("⬇️ Excel", excel_bytes, file_name="payment_tracker.xlsx")
    with col5:
        if selected_name != "All":
            to_number = CUSTOMER_WHATSAPP_MAP.get(selected_name, "")
            if not to_number:
                to_number = st.text_input(f"📱 WhatsApp for {selected_name}", value="+91", key="payment_whatsapp_number")
            if st.button("📤 WhatsApp Payment"):
                if not filtered.empty and to_number and to_number != "+91":
                    summary_lines = [
                        f"💰 Payment Summary for {selected_name}",
                        f"{'  Date  ':<12} {'  Paid  ':>6} {'  Discount  ':>9} {'  Total Paid  ':>12} {'  Remaining  ':>12}",
                        "-" * 60
                    ]
                    for row in filtered.to_dict(orient="records"):
                        summary_lines.append(f"{row['date']:<12} ₹{int(row['paid_amount']):>6} ₹{int(row['Discount']):>9} ₹{int(row['Total Paid']):>12} ₹{int(row['Remaining']):>12}")
                    if discount_amount:
                        summary_lines.append(f"\n🎁 Final Discount Applied: ₹{discount_amount}")
                        summary_lines.append(f"🧮 Final Remaining: ₹{remaining}")
                    send_gupshup_whatsapp(selected_name, "\n".join(summary_lines), fallback_number=to_number)
                    st.success(f"✅ Sent to {to_number}")
                else:
                    st.warning("⚠️ No payments or number invalid.")

    if not filtered.empty:
        delete_idx = st.number_input("Delete row index", min_value=0, max_value=len(filtered) - 1, step=1)
        if st.button("❌ Delete Payment"):
            delete_payment(filtered.index[delete_idx])
            st.success("✅ Deleted"); st.rerun()
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
        if submitted and authenticate(username, password, load_users()):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.login_time = datetime.now()
            st.rerun()
        else:
            st.error("❌ Invalid credentials")

if __name__ == "__main__":
    main()
