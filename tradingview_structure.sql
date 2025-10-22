-- MySQL dump 10.13  Distrib 8.0.39, for Win64 (x86_64)
--
-- Host: localhost    Database: tradingview
-- ------------------------------------------------------
-- Server version	8.0.39

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `days`
--

DROP TABLE IF EXISTS `days`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `days` (
  `id` int NOT NULL AUTO_INCREMENT,
  `date` date NOT NULL,
  `week_id` int DEFAULT NULL,
  `entry_balance` double NOT NULL DEFAULT '0',
  `day_pl` double NOT NULL DEFAULT '0',
  `current_balance` double NOT NULL DEFAULT '0',
  `risk10` double NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `date` (`date`),
  KEY `idx_days_week` (`week_id`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `trades`
--

DROP TABLE IF EXISTS `trades`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `trades` (
  `id` int NOT NULL AUTO_INCREMENT,
  `day_id` int DEFAULT NULL,
  `symbol` text NOT NULL,
  `position_size` double NOT NULL,
  `entry_price` double NOT NULL,
  `exit_price` double NOT NULL,
  `stop_loss` double DEFAULT NULL,
  `take_profit` double DEFAULT NULL,
  `trade_date` date DEFAULT NULL,
  `profit` double GENERATED ALWAYS AS (((`exit_price` - `entry_price`) * `position_size`)) STORED,
  PRIMARY KEY (`id`),
  KEY `idx_trades_day` (`day_id`)
) ENGINE=InnoDB AUTO_INCREMENT=38 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = cp850 */ ;
/*!50003 SET character_set_results = cp850 */ ;
/*!50003 SET collation_connection  = cp850_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_bi_trades_attach_day` BEFORE INSERT ON `trades` FOR EACH ROW BEGIN
  DECLARE v_day_id INT;
  DECLARE v_week_id INT;
  DECLARE v_monday DATE;
  DECLARE v_sunday DATE;
  DECLARE v_prev_balance DECIMAL(12,2);

  IF NEW.trade_date IS NOT NULL AND NEW.day_id IS NULL THEN

    
    SELECT d.id INTO v_day_id
    FROM tradingview.days d
    WHERE d.`date` = NEW.trade_date
    LIMIT 1;

    IF v_day_id IS NULL THEN
      
      SET v_monday = DATE_SUB(NEW.trade_date, INTERVAL WEEKDAY(NEW.trade_date) DAY);
      SET v_sunday = DATE_ADD(v_monday, INTERVAL 6 DAY);

      
      SELECT w.id INTO v_week_id
      FROM tradingview.weeks w
      WHERE NEW.trade_date BETWEEN w.start_date AND w.end_date
      LIMIT 1;

      IF v_week_id IS NULL THEN
        INSERT INTO tradingview.weeks (start_date, end_date, starting_balance, week_pl)
        VALUES (v_monday, v_sunday, 2000.00, 0.00);
        SET v_week_id = LAST_INSERT_ID();
      END IF;

      
      SELECT d.current_balance
      INTO v_prev_balance
      FROM tradingview.days d
      WHERE d.`date` < NEW.trade_date
      ORDER BY d.`date` DESC
      LIMIT 1;

      IF v_prev_balance IS NULL THEN
        SELECT w.starting_balance INTO v_prev_balance
        FROM tradingview.weeks w
        WHERE w.id = v_week_id;
      END IF;

      
      INSERT INTO tradingview.days
        (`date`, week_id, entry_balance, day_pl, current_balance, risk10)
      VALUES
        (NEW.trade_date, v_week_id, v_prev_balance, 0,
         v_prev_balance, ROUND(v_prev_balance * 0.10, 2));

      SET v_day_id = LAST_INSERT_ID();
    END IF;

    SET NEW.day_id = v_day_id;
  END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = cp850 */ ;
/*!50003 SET character_set_results = cp850 */ ;
/*!50003 SET collation_connection  = cp850_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_ai_trades_recalc_day` AFTER INSERT ON `trades` FOR EACH ROW BEGIN
  
  UPDATE tradingview.days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = NEW.day_id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = NEW.day_id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2)
  WHERE d.id = NEW.day_id;

  
  UPDATE tradingview.weeks w
  JOIN tradingview.days d ON d.week_id = w.id
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM tradingview.days d2 WHERE d2.week_id = w.id), 0)
  WHERE d.id = NEW.day_id;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = cp850 */ ;
/*!50003 SET character_set_results = cp850 */ ;
/*!50003 SET collation_connection  = cp850_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_au_trades_recalc_day` AFTER UPDATE ON `trades` FOR EACH ROW BEGIN
  
  UPDATE tradingview.days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = d.id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = d.id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2)
  WHERE d.id IN (OLD.day_id, NEW.day_id);

  UPDATE tradingview.weeks w
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM tradingview.days d2 WHERE d2.week_id = w.id), 0)
  WHERE w.id IN (
    SELECT week_id FROM tradingview.days WHERE id IN (OLD.day_id, NEW.day_id)
  );
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = cp850 */ ;
/*!50003 SET character_set_results = cp850 */ ;
/*!50003 SET collation_connection  = cp850_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trg_ad_trades_recalc_day` AFTER DELETE ON `trades` FOR EACH ROW BEGIN
  UPDATE tradingview.days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = OLD.day_id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM tradingview.trades t WHERE t.day_id = OLD.day_id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2)
  WHERE d.id = OLD.day_id;

  UPDATE tradingview.weeks w
  JOIN tradingview.days d ON d.week_id = w.id
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM tradingview.days d2 WHERE d2.week_id = w.id), 0)
  WHERE d.id = OLD.day_id;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Temporary view structure for view `v_day_stats`
--

DROP TABLE IF EXISTS `v_day_stats`;
/*!50001 DROP VIEW IF EXISTS `v_day_stats`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_day_stats` AS SELECT 
 1 AS `date`,
 1 AS `trades_count`,
 1 AS `total_pl`,
 1 AS `avg_profit`,
 1 AS `wins`,
 1 AS `losses`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `weeks`
--

DROP TABLE IF EXISTS `weeks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `weeks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `starting_balance` double NOT NULL DEFAULT '2000',
  `week_pl` double NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'tradingview'
--

--
-- Dumping routines for database 'tradingview'
--

--
-- Final view structure for view `v_day_stats`
--

/*!50001 DROP VIEW IF EXISTS `v_day_stats`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_day_stats` AS select `all_days`.`ddate` AS `date`,count(`t`.`id`) AS `trades_count`,coalesce(sum(`t`.`profit`),0) AS `total_pl`,avg(`t`.`profit`) AS `avg_profit`,sum((case when (`t`.`profit` > 0) then 1 else 0 end)) AS `wins`,sum((case when (`t`.`profit` <= 0) then 1 else 0 end)) AS `losses` from (((select `days`.`date` AS `ddate` from `days` union select `trades`.`trade_date` AS `ddate` from `trades` where (`trades`.`trade_date` is not null)) `all_days` left join `days` `d` on((`d`.`date` = `all_days`.`ddate`))) left join `trades` `t` on(((`t`.`day_id` = `d`.`id`) or (`t`.`trade_date` = `all_days`.`ddate`)))) group by `all_days`.`ddate` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-10-21 22:25:49
