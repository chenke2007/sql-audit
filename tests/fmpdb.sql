SELECT TMP_PAGE.*, ROWNUM ROW_ID
  FROM (SELECT *
          FROM (SELECT *
                  FROM (SELECT BI.MODULE_NAME,
                               BI.MODULE_CODE,
                               BI.BILL_NAME,
                               BI.BILLS,
                               BI.BILL_TYPE,
                               BM.ID,
                               BM.CORP_ID,
                               BM.BILL_ID,
                               BM.OWNER,
                               BM.OWNER_NAME,
                               BM.CREATER,
                               BM.CREATER_NAME,
                               BM.CREATER_DEPT,
                               BM.CREATE_ORG,
                               BM.BILL_NO,
                               BM.REMARK,
                               BM.CREATER_POST,
                               BM.REQ_USER,
                               BM.REQ_USER_NAME,
                               BM.REQ_DEPT,
                               BM.REQ_POST,
                               BM.REQ_ORG,
                               BM.URGENCY,
                               BM.EXCHANGE_RATE,
                               BM.BASE_CURRENCY,
                               BM.BASE_CURRENCY_UPPER,
                               BM.ORIGINAL_CURRENCY,
                               BM.ORIGINAL_CURRENCY_SUM,
                               BM.ORIGINAL_CURRENCY_UPPER,
                               BM.SIGNER,
                               BM.SUMMARY,
                               TO_CHAR(BM.FINISH_TASK_TIME, 'YYYY-MM-DD') FINISH_TASK_TIME,
                               BM.TRV_TRIP_ID,
                               BM.ITEM01,
                               BM.ITEM02,
                               BM.ITEM03,
                               BM.ITEM04,
                               BM.ITEM05,
                               BM.ITEM06,
                               BM.ITEM07,
                               BM.ITEM08,
                               BM.ITEM09,
                               BM.ITEM10,
                               BM.BILL_STATUS,
                               BM.SSC_BILL_STATUS,
                               BM.REQUEST_BILL_NO,
                               BM.RED_STATUS,
                               BM.RED_USER,
                               BM.RED_DATE,
                               BM.VOUCHER_FLAG,
                               BM.VOUCHER_DATE,
                               BM.ACCOUNT_DATE,
                               BM.TEMPLATE_ID,
                               BM.TEMPLATE_VERSION,
                               BM.FUND_BACK_STATUS,
                               BM.FUND_BACK_TIME,
                               BM.EXEMPT_REVIEW_FLAG,
                               BM.CONTRACT_ID,
                               BM.STS,
                               BM.CREATE_BY,
                               BM.MODIFY_BY,
                               SMP_CREATE_BY.NAME CREATOR_NAME,
                               BM.MODIFY_TIME,
                               SDP_REQ_DEPT.NAME DEPT_NAME,
                               SDP_REQ_ORG.NAME ORG_NAME,
                               SMP_REQ_USER.NAME REQ_USERNAME,
                               SMP_REQ_USER.NO REQ_USERNO,
                               TO_CHAR(BM.CREATE_TIME, 'YYYY-MM-DD') CREATE_TIME,
                               TO_CHAR(BM.SUBMIT_DATE, 'YYYY-MM-DD') SUBMIT_DATE,
                               (SELECT T.VALUE
                                  FROM T_SYS_DICT T
                                 WHERE T.BATCH_CODE = 'BILL_STATUS'
                                   AND T.KEY = BM.BILL_STATUS) BILL_STATUSNAME,
                               '/ecsBillDetail?pageStatus=billPreview&moduleCode=' ||
                               BI.MODULE_CODE || '&billId=' || BM.BILL_ID ||
                               '&mainId=' || BM.ID || '&isQueryDetailUrl=1' BILL_DETAIL_URL
                               
                              ,
                               (SELECT task.node_name
                                  FROM t_wf_person_task task
                                 WHERE task.business_key = BM.bill_No
                                   AND task.status = 'active'
                                   and rownum = 1) node_name,
                               (SELECT decode(task.node_name,
                                              '财务审批',
                                              '财务审核岗',
                                              '财务审核',
                                              '财务审核岗',
                                              '小微子公司财务',
                                              '小微子公司财务岗',
                                              task.assignee_name) assignee_name
                                  FROM t_wf_person_task task
                                 WHERE task.business_key = BM.bill_No
                                   AND task.status = 'active'
                                   and rownum = 1) assignee_name,
                               
                               BM.ITEM13,
                               BM.ITEM14
                          FROM T_BILL_INFO BI, T_ECS_BILL_MAIN BM
                          LEFT JOIN T_SYS_EMP SMP_CREATE_BY
                            ON SMP_CREATE_BY.ID = BM.CREATE_BY
                          LEFT JOIN T_SYS_EMP SMP_REQ_USER
                            ON SMP_REQ_USER.ID = BM.REQ_USER
                          LEFT JOIN T_SYS_DEPT SDP_REQ_DEPT
                            ON SDP_REQ_DEPT.ID = BM.REQ_DEPT
                          LEFT JOIN T_SYS_DEPT SDP_REQ_ORG
                            ON SDP_REQ_ORG.ID = BM.REQ_ORG
                         WHERE BI.ID = BM.BILL_ID
                        union all
                        SELECT BI.MODULE_NAME,
                               BI.MODULE_CODE,
                               BI.BILL_NAME,
                               BI.BILLS,
                               BI.BILL_TYPE,
                               BM.ID,
                               BM.CORP_ID,
                               BM.BILL_ID,
                               BM.OWNER,
                               BM.OWNER_NAME,
                               BM.CREATER,
                               BM.CREATER_NAME,
                               BM.CREATER_DEPT,
                               BM.CREATE_ORG,
                               BM.BILL_NO,
                               BM.REMARK,
                               BM.CREATER_POST,
                               BM.REQ_USER,
                               BM.REQ_USER_NAME,
                               BM.REQ_DEPT,
                               BM.REQ_POST,
                               BM.REQ_ORG,
                               BM.URGENCY,
                               BM.EXCHANGE_RATE,
                               BM.BASE_CURRENCY,
                               BM.BASE_CURRENCY_UPPER,
                               BM.ORIGINAL_CURRENCY,
                               BM.ORIGINAL_CURRENCY_SUM,
                               BM.ORIGINAL_CURRENCY_UPPER,
                               '' SIGNER,
                               BM.SUMMARY,
                               TO_CHAR(BM.FINISH_TASK_TIME, 'YYYY-MM-DD') FINISH_TASK_TIME,
                               '' TRV_TRIP_ID,
                               BM.ITEM01,
                               BM.ITEM02,
                               BM.ITEM03,
                               BM.ITEM04,
                               BM.ITEM05,
                               BM.ITEM06,
                               BM.ITEM07,
                               BM.ITEM08,
                               BM.ITEM09,
                               BM.ITEM10,
                               BM.BILL_STATUS,
                               BM.SSC_BILL_STATUS,
                               BM.REQUEST_BILL_NO,
                               BM.RED_STATUS,
                               BM.RED_USER,
                               BM.RED_DATE,
                               BM.VOUCHER_FLAG,
                               BM.VOUCHER_DATE,
                               BM.ACCOUNT_DATE,
                               BM.TEMPLATE_ID,
                               BM.TEMPLATE_VERSION,
                               BM.FUND_BACK_STATUS,
                               BM.FUND_BACK_TIME,
                               BM.EXEMPT_REVIEW_FLAG,
                               '' CONTRACT_ID,
                               BM.STS,
                               BM.CREATE_BY,
                               BM.MODIFY_BY,
                               SMP_CREATE_BY.NAME CREATOR_NAME,
                               BM.MODIFY_TIME,
                               SDP_REQ_DEPT.NAME DEPT_NAME,
                               SDP_REQ_ORG.NAME ORG_NAME,
                               SMP_REQ_USER.NAME REQ_USERNAME,
                               SMP_REQ_USER.NO REQ_USERNO,
                               TO_CHAR(BM.CREATE_TIME, 'YYYY-MM-DD') CREATE_TIME,
                               '' SUBMIT_DATE,
                               (SELECT T.VALUE
                                  FROM T_SYS_DICT T
                                 WHERE T.BATCH_CODE = 'BILL_STATUS'
                                   AND T.KEY = BM.BILL_STATUS) BILL_STATUSNAME,
                               '/ecsBillDetail?pageStatus=billPreview&moduleCode=' ||
                               BI.MODULE_CODE || '&billId=' || BM.BILL_ID ||
                               '&mainId=' || BM.ID || '&isQueryDetailUrl=1' BILL_DETAIL_URL
                               
                              ,
                               (SELECT task.node_name
                                  FROM t_wf_person_task task
                                 WHERE task.business_key = BM.bill_No
                                   AND task.status = 'active'
                                   and rownum = 1) node_name,
                               (SELECT decode(task.node_name,
                                              '财务审批',
                                              '财务审核岗',
                                              '财务审核',
                                              '财务审核岗',
                                              '小微子公司财务',
                                              '小微子公司财务岗',
                                              task.assignee_name) assignee_name
                                  FROM t_wf_person_task task
                                 WHERE task.business_key = BM.bill_No
                                   AND task.status = 'active'
                                   and rownum = 1) assignee_name,
                               '' item13,
                               '' item14
                          FROM T_BILL_INFO BI, T_trv_BILL_MAIN BM
                          LEFT JOIN T_SYS_EMP SMP_CREATE_BY
                            ON SMP_CREATE_BY.ID = BM.CREATE_BY
                          LEFT JOIN T_SYS_EMP SMP_REQ_USER
                            ON SMP_REQ_USER.ID = BM.REQ_USER
                          LEFT JOIN T_SYS_DEPT SDP_REQ_DEPT
                            ON SDP_REQ_DEPT.ID = BM.REQ_DEPT
                          LEFT JOIN T_SYS_DEPT SDP_REQ_ORG
                            ON SDP_REQ_ORG.ID = BM.REQ_ORG
                         WHERE BI.ID = BM.BILL_ID) FF
                 WHERE CORP_ID =
                       'SC202004291547466E5CB1C020DE4712BFE3BFF8C37ACD45')
        
         ORDER BY CREATE_TIME DESC, ID) TMP_PAGE
 WHERE ROWNUM <= 20;