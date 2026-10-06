<?xml version="1.0" encoding="UTF-8"?>
<!-- 计划只包含经过 Bash 预检的索引与值；用户字符串从不拼入 XPath。 -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" encoding="UTF-8" omit-xml-declaration="no"/>
  <xsl:variable name="plan" select="document('plan.xml')/plan"/>
  <xsl:template match="@*|node()">
    <xsl:copy><xsl:apply-templates select="@*|node()"/></xsl:copy>
  </xsl:template>
  <xsl:template match="application">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <xsl:if test="not(component[@name='ProjectJdkTable'])">
        <component name="ProjectJdkTable"><xsl:copy-of select="$plan/new/jdk"/></component>
      </xsl:if>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="project/component[@name='ProjectRootManager']">
    <xsl:copy>
      <xsl:apply-templates select="@*[name()!='project-jdk-name' and name()!='project-jdk-type']"/>
      <xsl:attribute name="project-jdk-name"><xsl:value-of select="$plan/@name"/></xsl:attribute>
      <xsl:attribute name="project-jdk-type">JavaSDK</xsl:attribute>
      <xsl:apply-templates select="node()"/>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="project/component[@name='GradleSettings']/option[@name='linkedExternalProjectsSettings']/GradleProjectSettings">
    <xsl:choose>
      <xsl:when test="count(preceding-sibling::GradleProjectSettings)+1 = number($plan/@gradle-index)">
        <xsl:copy>
          <xsl:apply-templates select="@*|node()[not(self::option[@name='gradleJvm'])]"/>
          <option name="gradleJvm"><xsl:attribute name="value"><xsl:value-of select="$plan/@name"/></xsl:attribute></option>
        </xsl:copy>
      </xsl:when>
      <xsl:otherwise><xsl:copy><xsl:apply-templates select="@*|node()"/></xsl:copy></xsl:otherwise>
    </xsl:choose>
  </xsl:template>
  <xsl:template match="module/component[@name='NewModuleRootManager']/orderEntry[@type='jdk']">
    <xsl:copy>
      <xsl:choose>
        <xsl:when test="@jdkName = $plan/alias/@name">
          <xsl:apply-templates select="@*[name()!='jdkName' and name()!='jdkType']"/>
          <xsl:attribute name="jdkName"><xsl:value-of select="$plan/@name"/></xsl:attribute>
          <xsl:attribute name="jdkType">JavaSDK</xsl:attribute>
        </xsl:when>
        <xsl:otherwise><xsl:apply-templates select="@*"/></xsl:otherwise>
      </xsl:choose>
      <xsl:apply-templates select="node()"/>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="application/component[@name='ProjectJdkTable']">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <xsl:if test="number($plan/@keep-index)=0"><xsl:copy-of select="$plan/new/jdk"/></xsl:if>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="application/component[@name='ProjectJdkTable']/jdk">
    <xsl:variable name="index" select="count(preceding-sibling::jdk)+1"/>
    <xsl:choose>
      <xsl:when test="$index = number($plan/@keep-index)">
        <xsl:copy>
          <xsl:apply-templates select="@*"/>
          <xsl:for-each select="node()">
            <xsl:choose>
              <xsl:when test="self::name">
                <xsl:copy><xsl:apply-templates select="@*[name()!='value']"/><xsl:attribute name="value"><xsl:value-of select="$plan/@name"/></xsl:attribute><xsl:apply-templates select="node()"/></xsl:copy>
              </xsl:when>
              <xsl:when test="self::homePath">
                <xsl:copy><xsl:apply-templates select="@*[name()!='value']"/><xsl:attribute name="value"><xsl:value-of select="$plan/@home"/></xsl:attribute><xsl:apply-templates select="node()"/></xsl:copy>
              </xsl:when>
              <xsl:otherwise><xsl:apply-templates select="."/></xsl:otherwise>
            </xsl:choose>
          </xsl:for-each>
        </xsl:copy>
      </xsl:when>
      <xsl:when test="$index = $plan/merge/@index"/>
      <xsl:otherwise><xsl:copy><xsl:apply-templates select="@*|node()"/></xsl:copy></xsl:otherwise>
    </xsl:choose>
  </xsl:template>
</xsl:stylesheet>
