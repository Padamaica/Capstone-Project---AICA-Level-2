# AI Finance Co-Pilot: AI output for 2026-09

- Python: 3.15.1
- LLM: ollama / qwen2.5:3b-instruct (ONLINE)
- Commentary source: llm:qwen2.5:3b-instruct accepted on attempt 1
- Unverified numbers flagged by numeric guard: []

## Validation
- Trial balance tallies: Dr = Cr = 680,560,578.72.
- Period covered: 01-Apr-2025 to 30-Sep-2026 (18 months).
- 3,633 rows, 1,530 vouchers, 26 ledgers.

## Management commentary

### Headline
Monthly MIS Commentary for Sep-2026

### Performance
- Revenue: ₹1.11 Cr, up 5.5% MoM and 24.7% YoY.
- Gross Margin: 47.1%, up 140 bps MoM.
- EBITDA: ₹30.16 L, EBITDA Margin: 27.3%.
- PAT: ₹21.17 L, PAT Margin: 19.1%.

### Budget Variance
- Revenue: ₹1.11 Cr vs budget ₹1.17 Cr (-5.5%).

### Cash & Working Capital
- Closing Cash: ₹2.36 Cr, up ₹76.91 L MoM.
- Cash from Operations: ₹77.91 L.
- Days Sales Outstanding (DSO): 45 days.
- Days Payable Outstanding (DPO): 35 days.
- Current Ratio: 5.36x.

### Risks & Anomalies
- Top Anomalies: 
  - Possible duplicate payment.
  - Expense spike in Professional Fees.
  - Unusually large entry in Professional Fees.

### Recommended Actions
1. Investigate the anomalies to ensure compliance and prevent future issues.
2. Monitor the cash inflows and outflows closely to maintain adequate liquidity.
3. Review and optimize the payment schedule to reduce DSO.
4. Enhance cash forecasting accuracy for better liquidity management.

## Ask your data (natural language to SQL)

### Q: What was the revenue trend in the last 6 months?
*Source: llm:qwen2.5:3b-instruct*  verified SQL; LLM answer rejected by numeric guard ['2025'], Python summary used

- month: 2026-09, revenue: ₹1.11 Cr
- month: 2026-08, revenue: ₹1.05 Cr
- month: 2026-07, revenue: ₹1.04 Cr
- month: 2026-06, revenue: ₹96.87 L
- month: 2026-05, revenue: ₹92.33 L
- month: 2026-04, revenue: ₹90.12 L

```sql
SELECT month, amount AS revenue FROM pnl WHERE line_item='Revenue' ORDER BY month DESC LIMIT 6
```

```text
  month     revenue
2026-09 11062189.81
2026-08 10489830.91
2026-07 10356181.20
2026-06  9686925.95
2026-05  9233336.43
2026-04  9012128.44
```

### Q: Which customers have the highest overdue receivables?
*Source: llm:qwen2.5:3b-instruct*  verified SQL

- Bharat Distributors: ₹6.53 L overdue
- Himalaya Stores: ₹1.25 L overdue
- Deccan Industries: ₹3.91 L overdue
- Apex Retail Ltd: ₹0 overdue
- Eastern Exports Co: ₹0 overdue
- Coastal Traders: ₹0 overdue
- Futura Engineering: ₹0 overdue
- Global Parts GmbH: ₹0 overdue

```sql
SELECT party, ROUND(SUM(open_amount),2) AS total_open, ROUND(SUM(CASE WHEN age_days>60 THEN open_amount ELSE 0 END),2) AS over_60_days, MAX(age_days) AS oldest_days FROM ar_ageing GROUP BY party ORDER BY over_60_days DESC, total_open DESC LIMIT 10
```

```text
              party  total_open  over_60_days  oldest_days
Bharat Distributors  2295522.69     653032.71           70
  Deccan Industries  3178388.34     391019.66           92
    Himalaya Stores  4234969.03     125267.81           68
 Eastern Exports Co  2365447.75          0.00           48
    Apex Retail Ltd  2347491.65          0.00           37
    Coastal Traders  2114505.47          0.00           27
 Futura Engineering  1893885.20          0.00           34
  Global Parts GmbH   961773.87          0.00           48
```

### Q: What were the top 5 expenses in the latest month?
*Source: llm:qwen2.5:3b-instruct*  verified SQL

- Purchases - Raw Material: ₹55.32 L
- Salaries & Wages: ₹12.81 L
- Income Tax: ₹7.06 L
- Freight Inward: ₹3.19 L
- Rent: ₹2.50 L

```sql
SELECT account, category, ROUND(SUM(debit-credit),2) AS amount FROM gl WHERE statement='PL' AND category NOT IN ('Revenue','Other Income') AND month=(SELECT MAX(month) FROM pnl) GROUP BY account, category ORDER BY amount DESC LIMIT 5
```

```text
                 account       category     amount
Purchases - Raw Material           COGS 5532387.25
        Salaries & Wages  Employee Cost 1281154.52
              Income Tax            Tax  705602.34
          Freight Inward           COGS  319326.21
                    Rent Admin Expenses  250000.00
```

### Q: How has closing cash moved over the last 6 months?
*Source: llm:qwen2.5:3b-instruct*  verified SQL

- 2026-09: ₹2.36 Cr
- 2026-08: ₹1.59 Cr
- 2026-07: ₹1.60 Cr
- 2026-06: ₹1.43 Cr
- 2026-05: ₹1.67 Cr
- 2026-04: ₹1.52 Cr

```sql
SELECT month, amount AS closing_cash FROM balance_sheet WHERE line_item='Cash & Bank' ORDER BY month DESC LIMIT 6
```

```text
  month  closing_cash
2026-09   23571929.83
2026-08   15881299.99
2026-07   16017871.47
2026-06   14289049.62
2026-05   16742175.75
2026-04   15169672.88
```

### Q: What was depreciation in each of the last 3 months?
*Source: llm:qwen2.5:3b-instruct*  LLM-written SQL (attempt 1)

- 2026-09: ₹1.81 L

```sql
SELECT month, amount FROM pnl WHERE month IN (SELECT month FROM gl WHERE line_item='Depreciation' ORDER BY month DESC LIMIT 3)
```

```text
  month   amount
2026-09 181250.0
```