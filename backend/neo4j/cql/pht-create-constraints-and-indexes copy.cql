/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
//
// Creating constraints and indexes for WHO Disease Outbreak News articles
//
CREATE CONSTRAINT url_don IF NOT EXISTS FOR (n:DON) REQUIRE n.url IS UNIQUE;
CREATE TEXT INDEX summary_don IF NOT EXISTS FOR (n:DON) ON (n.summary);
CREATE TEXT INDEX content_don IF NOT EXISTS FOR (n:DON) ON (n.content);
//
//
// Public Health Threat
//
CREATE CONSTRAINT text_threat IF NOT EXISTS FOR (n:Threat) REQUIRE n.text IS UNIQUE;
//
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
