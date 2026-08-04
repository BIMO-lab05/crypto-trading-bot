--
-- PostgreSQL database dump
--

\restrict elmwCKx2eFPFwMoos3P39PjE3G7opsdoC5Pp3ElE8A8LVXTK44VRvcrzJ7AyGld

-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: portfolios; Type: TABLE DATA; Schema: public; Owner: cryptobot
--

INSERT INTO public.portfolios (id, portfolio_id, name, initial_balance, cash_balance, total_value, total_pnl, total_return_pct, sharpe_ratio, max_drawdown, win_rate, created_at, updated_at, realized_pnl, unrealized_pnl, is_active, trading_mode, risk_per_trade, max_daily_loss) VALUES (1, 'paper_trading', 'Paper Trading Portfolio', 10000.00000000, 78.78460225, 100.00000000, 0.00000000, 0.0000, NULL, NULL, NULL, '2026-04-27 02:00:48.196184', '2026-07-31 16:28:18.320752', -1.25380976, 0.00000000, true, 'PAPER', 0.0200, 0.0500);


--
-- Data for Name: positions; Type: TABLE DATA; Schema: public; Owner: cryptobot
--

INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (47, '826f5b17-460e-455d-a648-f7708201339f', 'paper_trading', 'BTCUSDT', 'SHORT', 0.00074698, 63556.10000000, 63556.10000000, NULL, 47.47500000, 0.00000000, NULL, 64827.22200000, 61013.85600000, 'OPEN', 'ensemble', NULL, '2026-07-29 20:00:42.322091', NULL, '2026-07-29 20:00:42.344047', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (49, 'b2c6ab66-acb6-43af-916e-bd85ea336b78', 'paper_trading', 'BNBUSDT', 'LONG', 0.11067325, 593.60000000, 593.60000000, NULL, 65.69563845, 0.00000000, NULL, 581.72800000, 617.34400000, 'OPEN', 'ensemble', NULL, '2026-07-30 17:38:07.844994', NULL, '2026-07-30 17:38:08.069839', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (46, 'e383636c-5fa5-4bce-9890-5f7606916790', 'paper_trading', 'SOLUSDT', 'SHORT', 0.68268706, 73.24000000, 73.24000000, 75.07832400, 50.00000000, 0.00000000, -1.25500001, 74.70480000, 70.31040000, 'CLOSED', 'ensemble', 'Market buy order (SHORT close) [stop_loss_limit]', '2026-07-29 17:18:55.857953', '2026-07-30 20:12:33.86205', '2026-07-30 20:12:34.021741', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (48, 'b15d95bc-9a94-40f1-aba2-14a0f456be37', 'paper_trading', 'ETHUSDT', 'SHORT', 0.02789966, 1883.10000000, 1883.10000000, 1930.36581000, 52.53784082, 0.00000000, -1.31870003, 1920.76200000, 1807.77600000, 'CLOSED', 'ensemble', 'Market buy order (SHORT close) [stop_loss_limit]', '2026-07-29 21:00:42.179691', '2026-07-30 20:12:38.341936', '2026-07-30 20:12:38.346526', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (51, '072b601f-1396-40d4-ac34-22739d0f99d5', 'paper_trading', 'ETHUSDT', 'LONG', 0.04483952, 1861.84000000, 1861.84000000, NULL, 83.48401718, 0.00000000, NULL, 1824.60320000, 1936.31360000, 'OPEN', 'ensemble', NULL, '2026-07-31 16:27:36.068094', NULL, '2026-07-31 16:27:36.091681', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (50, '05156906-238f-4ac4-af40-15251caf7976', 'paper_trading', 'ADAUSDT', 'LONG', 292.24495398, 0.17230000, 0.17230000, 0.16800973, 50.35380557, 0.00000000, -1.25380976, 0.16885400, 0.17919200, 'CLOSED', 'ensemble', 'Market sell order (LONG close) [stop_loss_limit]', '2026-07-30 19:33:20.932097', '2026-07-31 16:28:18.311589', '2026-07-31 16:28:18.320838', NULL);
INSERT INTO public.positions (id, position_id, portfolio_id, symbol, side, quantity, entry_price, current_price, exit_price, cost_basis, unrealized_pnl, realized_pnl, stop_loss, take_profit, status, strategy, exit_reason, opened_at, closed_at, updated_at, entry_signal_confidence) VALUES (52, 'fb990293-7623-4265-a9d8-b11acc13148c', 'paper_trading', 'SOLUSDT', 'LONG', 1.07850243, 73.05000000, 73.05000000, NULL, 78.78460225, 0.00000000, NULL, 71.58900000, 75.97200000, 'OPEN', 'ensemble', NULL, '2026-07-31 16:28:24.437229', NULL, '2026-07-31 16:28:24.441266', NULL);


--
-- Data for Name: trades; Type: TABLE DATA; Schema: public; Owner: cryptobot
--

INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (63, '3cfbcb42-b9d5-48ef-aaea-eec9f4f59062', 'paper_trading', 'SOLUSDT', 'SELL', 0.68268706, 73.24000000, 50.00000000, 0.05000000, NULL, 'ensemble', 0.1118, '2026-07-29 17:18:55.996863', '{"order_type": "MARKET", "position_id": "e383636c-5fa5-4bce-9890-5f7606916790"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (64, 'e65615a1-3f14-4942-90ac-4987417e4c64', 'paper_trading', 'BTCUSDT', 'SELL', 0.00074698, 63556.10000000, 47.47500000, 0.04747500, NULL, 'ensemble', 0.1262, '2026-07-29 20:00:42.338627', '{"order_type": "MARKET", "position_id": "826f5b17-460e-455d-a648-f7708201339f"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (65, '5776d24e-114a-410e-8d96-4bd081b1cd25', 'paper_trading', 'ETHUSDT', 'SELL', 0.02789966, 1883.10000000, 52.53784082, 0.05253784, NULL, 'ensemble', 0.1575, '2026-07-29 21:00:42.196935', '{"order_type": "MARKET", "position_id": "b15d95bc-9a94-40f1-aba2-14a0f456be37"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (66, '0c63fa13-44b2-44ba-88ef-06ea59c0db3d', 'paper_trading', 'BNBUSDT', 'BUY', 0.11067325, 593.60000000, 65.69563845, 0.06569564, NULL, 'ensemble', 0.2093, '2026-07-30 17:38:07.964668', '{"order_type": "MARKET", "position_id": "b2c6ab66-acb6-43af-916e-bd85ea336b78"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (67, 'a82303f4-6949-4261-812a-1d6bf828aa87', 'paper_trading', 'ADAUSDT', 'BUY', 292.24495398, 0.17230000, 50.35380557, 0.05035381, NULL, 'ensemble', 0.1740, '2026-07-30 19:33:21.030908', '{"order_type": "MARKET", "position_id": "05156906-238f-4ac4-af40-15251caf7976"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (68, '4bbcfe08-7168-47ea-bf48-ce449b14e79b', 'paper_trading', 'SOLUSDT', 'BUY', 0.68268706, 75.07832400, 51.25500028, 0.05125500, -1.25500001, 'stop_loss_limit', NULL, '2026-07-30 20:12:33.899276', '{"order_type": "MARKET", "position_id": "e383636c-5fa5-4bce-9890-5f7606916790"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (69, '0c0fc353-829e-42ce-872e-6670addeb11a', 'paper_trading', 'ETHUSDT', 'BUY', 0.02789966, 1930.36581000, 53.85654977, 0.05385655, -1.31870003, 'stop_loss_limit', NULL, '2026-07-30 20:12:38.34351', '{"order_type": "MARKET", "position_id": "b15d95bc-9a94-40f1-aba2-14a0f456be37"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (70, '33e4483f-e374-465c-b5ab-92514eaa62cf', 'paper_trading', 'ETHUSDT', 'BUY', 0.04483952, 1861.84000000, 83.48401718, 0.08348402, NULL, 'ensemble', 0.3628, '2026-07-31 16:27:36.075212', '{"order_type": "MARKET", "position_id": "072b601f-1396-40d4-ac34-22739d0f99d5"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (71, 'f8b40e8f-aedf-4746-adf9-2f6f19162130', 'paper_trading', 'ADAUSDT', 'SELL', 292.24495398, 0.16800973, 49.09999581, 0.04910000, -1.25380976, 'stop_loss_limit', NULL, '2026-07-31 16:28:18.31331', '{"order_type": "MARKET", "position_id": "05156906-238f-4ac4-af40-15251caf7976"}');
INSERT INTO public.trades (id, trade_id, portfolio_id, symbol, side, quantity, price, total_value, fee, realized_pnl, strategy, signal_confidence, executed_at, metadata) VALUES (72, 'b2def19d-a742-42a8-b87c-275fc739f1a4', 'paper_trading', 'SOLUSDT', 'BUY', 1.07850243, 73.05000000, 78.78460225, 0.07878460, NULL, 'ensemble', 0.2927, '2026-07-31 16:28:24.439116', '{"order_type": "MARKET", "position_id": "fb990293-7623-4265-a9d8-b11acc13148c"}');


--
-- Name: portfolios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: cryptobot
--

SELECT pg_catalog.setval('public.portfolios_id_seq', 2, true);


--
-- Name: positions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: cryptobot
--

SELECT pg_catalog.setval('public.positions_id_seq', 52, true);


--
-- Name: trades_id_seq; Type: SEQUENCE SET; Schema: public; Owner: cryptobot
--

SELECT pg_catalog.setval('public.trades_id_seq', 72, true);


--
-- PostgreSQL database dump complete
--

\unrestrict elmwCKx2eFPFwMoos3P39PjE3G7opsdoC5Pp3ElE8A8LVXTK44VRvcrzJ7AyGld

