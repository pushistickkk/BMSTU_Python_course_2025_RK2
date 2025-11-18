import os
import time
import math
import requests
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


BASE_URL = "http://193.233.171.205:5000"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# хардкоженные криды
DEFAULT_USERS = {
    'manager_ts': {
        'role': 'manager',
        'code': "DeF34mNo56Pq"
    },
    'manager_sa': {
        'role': 'manager', 
        'code': "GhI78wXy12Rt"
    }
}
ANALYST = {
    'login': 'analyst_sa',
    'code': 'BcD01oLm23Kl'
}

ENDPOINT_TICKETS = '/api/v1/tickets'
ENDPOINT_TICKET = '/api/v1/tickets/{}'
ENDPOINT_CATEGORIES = '/api/v1/categories'

REQUEST_TIMEOUT = 10
SLEEP_BETWEEN_REQ = 0.1

def safe_get(url, params=None):
    """
    Performs a safe GET request with error handling and timeout.
    
    @param url: The URL to make the request to
    @param params: Optional query parameters for the request
    @return: JSON response as dictionary or None if request failed
    """
    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        try:
            return r.json()
        except json.JSONDecodeError:
            print(f"Warning: received non-json from {url}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return None


def fetch_all_tickets(login, code):
    """
    Fetches all tickets assigned to the specified user from the API.
    
    @param login: Username for authentication
    @param code: Password for authentication  
    @return: List of ticket dictionaries or empty list if request failed
    """
    url = BASE_URL + ENDPOINT_TICKETS
    params = { 'login': login, 'code': code }

    all_tickets = []
    data = safe_get(url, params=params)
    time.sleep(SLEEP_BETWEEN_REQ)
    if not data:
        return all_tickets
    all_tickets.extend(data)

    return all_tickets


def fetch_ticket_detail(ticket_id, login, code):
    """
    Fetches detailed information for a specific ticket by ID.
    
    @param ticket_id: The unique identifier of the ticket
    @param login: Username for authentication
    @param code: Password for authentication
    @return: Ticket details as dictionary or None if request failed
    """
    url = BASE_URL + ENDPOINT_TICKET.format(ticket_id)
    params = { 'login': login, 'code': code }
    data = safe_get(url, params=params)
    time.sleep(SLEEP_BETWEEN_REQ)
    return data


def fetch_categories(login, code):
    """
    Fetches the list of ticket categories from the API.
    
    @param login: Username for authentication
    @param code: Password for authentication
    @return: List of categories or None if request failed
    """
    url = BASE_URL + ENDPOINT_CATEGORIES
    params = { 'login': login, 'code': code }
    return safe_get(url, params=params)


def build_dataframe(tickets, fetch_details=False, detail_login=None, detail_code=None):
    """
    Converts a list of tickets into a pandas DataFrame with structured fields.
    
    @param tickets: List of ticket dictionaries
    @param fetch_details: Whether to fetch additional details for each ticket
    @param detail_login: Username for fetching ticket details
    @param detail_code: Password for fetching ticket details
    @return: pandas DataFrame with processed ticket data
    """
    rows = []
    for t in tickets:
        t_id = t.get('id') or t.get('ticket_id') or t.get('_id')
        created = t.get('created_at') or t.get('created')
        closed = t.get('closed_at') or t.get('closed')
        category = t.get('category') or t.get('category_name') or t.get('cat')
        priority = t.get('priority')
        status = t.get('status')

        if fetch_details and t_id and (not category or not closed):
            d = fetch_ticket_detail(t_id, detail_login, detail_code)
            if d:
                created = created or d.get('created_at') or d.get('created')
                closed = closed or d.get('closed_at') or d.get('closed')
                category = category or d.get('category') or d.get('category_name')
                priority = priority or d.get('priority')
                status = status or d.get('status')

        rows.append({
            'ticket_id': t_id,
            'created_at': created,
            'closed_at': closed,
            'category': category,
            'priority': priority,
            'status': status,
            'raw': t
        })

    df = pd.DataFrame(rows)

    for col in ['created_at', 'closed_at']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    if 'created_at' in df.columns:
        df['created_date'] = df['created_at'].dt.date
        df['created_day'] = df['created_at'].dt.day
        df['created_hour'] = df['created_at'].dt.hour
        df['created_weekday'] = df['created_at'].dt.weekday  # 0=Monday
        df['created_weekday_name'] = df['created_at'].dt.day_name()

    if 'closed_at' in df.columns:
        df['resolution_time'] = (df['closed_at'] - df['created_at']).dt.total_seconds() / 3600.0  # hours
    else:
        df['resolution_time'] = np.nan

    return df


def plot_daily_trend(df, days=30, outpath=None):
    """
    Creates a line chart showing ticket creation trends over the specified number of days.
    
    @param df: DataFrame containing ticket data
    @param days: Number of days to include in the trend analysis
    @param outpath: Output file path for saving the chart
    """
    if outpath is None:
        outpath = os.path.join(OUTPUT_DIR, 'line_daily_tickets.png')

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days-1)

    daily = df.dropna(subset=['created_date']).groupby('created_date').size().reindex(
        pd.date_range(start, today).date, fill_value=0
    )

    plt.figure(figsize=(12, 6))
    plt.plot(daily.index, daily.values, marker='o', linewidth=2, color='#2E86AB', markersize=6)
    plt.title(f'Ticket Creation Trend by Day (Last {days} Days)\nTotal Tickets: {len(df)}', 
              fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Number of Tickets', fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved', outpath)


def plot_hourly_distribution(df, outpath=None):
    """
    Creates a bar chart showing ticket distribution across hours of the day.
    
    @param df: DataFrame containing ticket data
    @param outpath: Output file path for saving the chart
    """
    if outpath is None:
        outpath = os.path.join(OUTPUT_DIR, 'bar_hourly_distribution.png')

    hourly = df.groupby('created_hour').size().reindex(range(24), fill_value=0)
    plt.figure(figsize=(12, 6))
    bars = plt.bar(hourly.index, hourly.values, color='#A23B72', edgecolor='black', alpha=0.7)
    plt.title('Ticket Distribution by Hour of Day', fontsize=14, fontweight='bold')
    plt.xlabel('Hour of Day', fontsize=12)
    plt.ylabel('Number of Tickets', fontsize=12)
    plt.xticks(range(0, 24, 2))
    plt.grid(True, alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(outpath, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved', outpath)


def plot_heatmap_weekday_hour(df, outpath=None):
    """
    Creates a heatmap visualization of ticket activity by weekday and hour.
    
    @param df: DataFrame containing ticket data
    @param outpath: Output file path for saving the chart
    """
    if outpath is None:
        outpath = os.path.join(OUTPUT_DIR, 'heatmap_weekday_hour.png')

    pivot = df.pivot_table(index='created_weekday', columns='created_hour', 
                          values='ticket_id', aggfunc='count', fill_value=0)
    pivot = pivot.reindex(index=range(0,7), columns=range(0,24), fill_value=0)

    weekday_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] # for bar distribution

    plt.figure(figsize=(14, 6))
    sns.heatmap(pivot, annot=True, fmt='d', cmap='YlOrRd', 
                cbar_kws={'label': 'Number of Tickets'},
                xticklabels=2, yticklabels=weekday_names)
    plt.title('Heatmap: Activity by Weekday and Hour', fontsize=14, fontweight='bold')
    plt.xlabel('Hour of Day', fontsize=12)
    plt.ylabel('Day of Week', fontsize=12)
    plt.tight_layout()
    plt.savefig(outpath, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved', outpath)


def plot_pie_by_category(df, outpath=None):
    """
    Creates a pie chart showing distribution of tickets across problem categories.
    
    @param df: DataFrame containing ticket data
    @param outpath: Output file path for saving the chart
    """
    if outpath is None:
        outpath = os.path.join(OUTPUT_DIR, 'pie_by_category.png')

    cat_series = df['category'].fillna('(unknown)')
    counts = cat_series.value_counts()

    def shorten_label(label, max_length=20):
        if len(str(label)) > max_length:
            return str(label)[:max_length-3] + '...'
        return str(label)

    labels = [shorten_label(label) for label in counts.index.tolist()]
    sizes = counts.values

    plt.figure(figsize=(10, 8))
    colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
    wedges, texts, autotexts = plt.pie(sizes, labels=labels, autopct='%1.1f%%', 
                                      startangle=90, colors=colors)
    
    for autotext in autotexts:
        autotext.set_color('black')
        autotext.set_fontweight('bold')
    
    plt.title('Ticket Distribution by Problem Category', fontsize=14, fontweight='bold')
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(outpath, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved', outpath)


def plot_avg_resolution_by_category(df, outpath=None):
    """
    Creates a horizontal bar chart showing average resolution time by category.
    
    @param df: DataFrame containing ticket data
    @param outpath: Output file path for saving the chart
    """
    if outpath is None:
        outpath = os.path.join(OUTPUT_DIR, 'avg_resolution_by_category.png')

    df_res = df.dropna(subset=['resolution_time'])
    if df_res.empty:
        print('No closed tickets with resolution_time to plot')
        # Create placeholder
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No data on closed tickets\nfor resolution time analysis', 
                ha='center', va='center', transform=plt.gca().transAxes, fontsize=12)
        plt.title('Average Resolution Time by Category', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(outpath, dpi=300, bbox_inches='tight')
        plt.close()
        print('Saved empty chart to', outpath)
        return

    avg_by_cat = df_res.groupby('category')['resolution_time'].mean().sort_values()

    plt.figure(figsize=(12, 8))
    bars = plt.barh(range(len(avg_by_cat)), avg_by_cat.values, color='#F18F01', alpha=0.7)
    plt.yticks(range(len(avg_by_cat)), [str(label) for label in avg_by_cat.index])
    plt.xlabel('Average Resolution Time (hours)', fontsize=12)
    plt.title('Average Ticket Resolution Time by Category', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3, axis='x')
    

    for i, bar in enumerate(bars):
        width = bar.get_width()
        plt.text(width + 0.1, bar.get_y() + bar.get_height()/2.,
                f'{width:.1f} h', ha='left', va='center', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(outpath, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved', outpath)


def top_n_categories(df, n=5, outpath=None):
    """
    Identifies and returns the top N categories by ticket count.
    
    @param df: DataFrame containing ticket data
    @param n: Number of top categories to return
    @param outpath: Optional output file path for saving results as CSV
    @return: pandas Series with top categories and their counts
    """
    counts = df['category'].fillna('(unknown)').value_counts().head(n)
    if outpath:
        counts.to_csv(outpath, header=['count'], encoding='utf-8-sig')
        print('Saved', outpath)
    return counts


def print_detailed_stats(df):
    """
    Prints comprehensive statistics about the ticket data.
    
    @param df: DataFrame containing ticket data for analysis
    """
    print(f"\n{'='*60}")
    print("DETAILED STATISTICS")
    print(f"{'='*60}")
    print(f"Total tickets: {len(df)}")
    print(f"Data period: from {df['created_at'].min().strftime('%Y-%m-%d')} to {df['created_at'].max().strftime('%Y-%m-%d')}")
    print(f"Unique categories: {df['category'].nunique()}")
    
    if 'status' in df.columns:
        print(f"\nStatus distribution:")
        status_counts = df['status'].value_counts()
        for status, count in status_counts.items():
            print(f"  - {status}: {count}")
    
    closed_tickets = df.dropna(subset=['closed_at'])
    if not closed_tickets.empty:
        avg_resolution = closed_tickets['resolution_time'].mean()
        print(f"Average resolution time: {avg_resolution:.1f} hours")
        print(f"Closed tickets: {len(closed_tickets)}")


def main():
    """
    Main function that orchestrates the entire analytics pipeline.
    Fetches data, processes it, and generates all visualizations and reports.
    """

    print('Fetching categories using analyst account...')
    cats = fetch_categories(ANALYST['login'], ANALYST['code'])
    print('Categories response:', type(cats))


    all_tickets = []
    for login, info in DEFAULT_USERS.items():
        print('Fetching tickets for', login)
        tickets = fetch_all_tickets(login, info['code'])
        print(f'  got {len(tickets)} tickets for {login}')
        all_tickets.extend(tickets)

    if not all_tickets:
        print('No tickets available to analyze. Exiting.')
        return
    
    # print(all_tickets)

    df = build_dataframe(all_tickets, fetch_details=False, 
                        detail_login=ANALYST['login'], detail_code=ANALYST['code'])
    print('Constructed DataFrame with', len(df), 'rows')
    print(df)


    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=29)
    df_last30 = df[df['created_at'] >= pd.Timestamp(since)] if 'created_at' in df.columns else df


    plot_daily_trend(df_last30, days=30, outpath=os.path.join(OUTPUT_DIR, 'line_daily_tickets.png'))
    plot_hourly_distribution(df, outpath=os.path.join(OUTPUT_DIR, 'bar_hourly_distribution.png'))
    plot_heatmap_weekday_hour(df, outpath=os.path.join(OUTPUT_DIR, 'heatmap_weekday_hour.png'))
    plot_pie_by_category(df, outpath=os.path.join(OUTPUT_DIR, 'pie_by_category.png'))
    plot_avg_resolution_by_category(df, outpath=os.path.join(OUTPUT_DIR, 'avg_resolution_by_category.png'))


    top5 = top_n_categories(df, n=5, outpath=os.path.join(OUTPUT_DIR, 'top5_categories.csv'))
    print('\nTop-5 categories by ticket count:')
    print(top5)
    print_detailed_stats(df)
    print(f'\nAll charts saved to folder: {OUTPUT_DIR}')

if __name__ == '__main__':
    main()